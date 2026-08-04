import tkinter as tk
from tkinter import ttk
from collections import defaultdict
from datetime import datetime, timezone
from itertools import zip_longest

import json
import os.path
import requests

import locale

from tkinter import *

import time
from datetime import datetime as dt

locale.setlocale(locale.LC_ALL, "")  # Use '' for auto, or force e.g. to 'en_US.UTF-8'

AGENT_FILE = "agents.json"

API_STATUS = "https://api.spacetraders.io/v2/"
LIST_FACTIONS = "https://api.spacetraders.io/v2/factions"
CLAIM_USER = "https://api.spacetraders.io/v2/register"
MY_ACCOUNT = "https://api.spacetraders.io/v2/my/agent"
MY_CONTRACTS = "https://api.spacetraders.io/v2/my/contracts"
MY_SHIPS = "https://api.spacetraders.io/v2/my/ships"

UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
DISPLAY_FORMAT = " %B, %Y"

FACTION_LOOKUPS = {}


past_scanned_waypoints = {}
past_markets = {}

nav_info_job = None

def parse_datetime(dt):
    return datetime.strptime(dt, UTC_FORMAT)


def format_datetime(dt_text):
    dt = parse_datetime(dt_text)
    d = dt.day
    return (
        str(d)
        + ("th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th"))
        + datetime.strftime(dt, DISPLAY_FORMAT)
    )


def load_player_logins():
    known_agents = {}

    if os.path.exists(AGENT_FILE):
        with open(AGENT_FILE) as json_agents:
            known_agents = json.load(json_agents)

    return known_agents


def store_agent_login(json_result):
    known_agents = load_player_logins()
    known_agents[json_result["symbol"]] = json_result["token"]

    with open(AGENT_FILE, "w") as json_agents:
        json.dump(known_agents, json_agents)


def get_faction_lookups():
    global FACTION_LOOKUPS
    if len(FACTION_LOOKUPS) > 0:
        return FACTION_LOOKUPS

    try:
        response = requests.get(
            LIST_FACTIONS,
            params={"limit": 20},
        )

        if response.status_code == 200:
            faction_json = response.json()
            for faction in faction_json["data"]:
                FACTION_LOOKUPS[faction["symbol"]] = faction["name"]

        else:
            print("Failed:", response.status_code, response.reason, response.text)

    except ConnectionError as ce:
        print("Failed:", ce)

    return FACTION_LOOKUPS



def generate_faction_combobox():
    faction_combobox["values"] = sorted(get_faction_lookups().values())

def generate_purchase_type_combobox():
    market_purchase_type_combobox["values"] = ["Exports","Imports","Exchange (Buy)", "Exchange (Sell)"]

def generate_login_combobox():
    known_agents = load_player_logins()
    agent_list = sorted(known_agents.keys(), key=str.casefold)

    id_login["values"] = agent_list


def show_agent_summary(json_result):
    global FACTION_LOOKUPS
    tabs.tab(0, state=tk.DISABLED)
    tabs.tab(1, state=tk.NORMAL)
    tabs.tab(2, state=tk.NORMAL)
    tabs.tab(3, state=tk.NORMAL)
    tabs.tab(4, state=tk.NORMAL)

    player_token.set(json_result["token"])
    player_login.set(json_result["symbol"])
    player_faction.set(get_faction_lookups()[json_result["startingFaction"]])
    player_worth.set(f"{json_result['credits']:n}")

    tabs.select(1)


def register_agent():
    try:
        username = agent_name.get()
        faction = next(
            iter(
                [
                    symbol
                    for symbol, name in get_faction_lookups().items()
                    if name == agent_faction.get()
                ]
            )
        )

        response = requests.post(
            CLAIM_USER,
            data={"faction": faction, "symbol": username},
        )
        if response.status_code < 400:
            result = response.json()
            # used to hold the token for later
            result["data"]["agent"]["token"] = result["data"]["token"]
            store_agent_login(result["data"]["agent"])
            show_agent_summary(result["data"]["agent"])
            agent_name.set("")
        else:
            print("Failed:", response.status_code, response.reason, response.text)

    except StopIteration:
        print("Did they pick a faction?")

    except ConnectionError as ce:
        print("Failed:", ce)


def login_agent():
    player_token.set(player_login.get())

    # -1 -> user entered a new token, so there won't be a name selected
    if id_login.current() != -1:
        known_agents = load_player_logins()
        player_token.set(known_agents[player_login.get()])

    try:
        response = requests.get(
            MY_ACCOUNT,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )
        if response.status_code == 200:
            result = response.json()
            # used to hold the token for later
            result["data"]["token"] = player_token.get()
            show_agent_summary(result["data"])
            # print(result)

            # -1, so now store the agent name / token for future runs
            if id_login.current() == -1:
                store_agent_login(result["data"])

        else:
            print("Failed:", response.status_code, response.reason, response.text)

    except ConnectionError as ce:
        print("Failed:", ce)


def logout_agent():
    tabs.tab(0, state=tk.NORMAL)
    tabs.tab(1, state=tk.DISABLED)
    tabs.tab(2, state=tk.DISABLED)
    tabs.tab(3, state=tk.DISABLED)
    tabs.tab(4, state=tk.DISABLED)
    
    player_login.set("")
    player_token.set("")

    tabs.select(0)


def refresh_tabs(event):
    selected_index = tabs.index(tabs.select())
    if selected_index == 1:
        refresh_player_summary()

    elif selected_index == 2:
        refresh_leaderboard()
    
    elif selected_index == 3:
        refresh_ships()

    elif selected_index == 4:
        refresh_marketplace()



def refresh_player_summary(*args):
    try:
        response = requests.get(
            MY_ACCOUNT,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )
        if response.status_code == 200:
            result = response.json()

            player_worth.set(f"{result['data']['credits']:n}")

        response = requests.get(
            MY_CONTRACTS,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )
        if response.status_code == 200:
            result = response.json()
            contract_view.delete(*contract_view.get_children())
            for row in result["data"]:
                if len(row["terms"]["deliver"]) > 0:
                    remaining = (
                        row["terms"]["deliver"][0]["unitsRequired"]
                        - row["terms"]["deliver"][0]["unitsFulfilled"]
                    )
                    contract_view.insert(
                        "",
                        "end",
                        iid=row["id"],
                        text="contract_values",
                        open=True,
                        values=(
                            get_faction_lookups()[row["factionSymbol"]],
                            row["type"],
                            format_datetime(row["terms"]["deadline"]),
                            row["terms"]["deliver"][0]["tradeSymbol"],
                            row["terms"]["deliver"][0]["destinationSymbol"],
                            f"{remaining:n}",
                        ),
                    )
                for subrow, item in enumerate(row["terms"]["deliver"][1:]):
                    contract_view.insert(
                        row["id"],
                        "end",
                        iid=f'{row["id"]}#{subrow}',
                        text="extra_items",
                        values=(
                            "",
                            "",
                            "",
                            item["tradeSymbol"],
                            item["destinationSymbol"],
                            f"{(item['unitsRequired']-item['unitsFulfilled']):n}",
                        ),
                    )

        else:
            print("Failed:", response.status_code, response.reason, response.text)

        response = requests.get(
            MY_SHIPS,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )
        if response.status_code == 200:
            result = response.json()
            ship_view.delete(*ship_view.get_children())
            for row in result["data"]:
                modules_and_mounts = list(
                    zip_longest(
                        row["modules"], row["mounts"], fillvalue=defaultdict(str)
                    )
                )
                if len(modules_and_mounts) > 0:
                    module, mount = modules_and_mounts[0]

                ship_view.insert(
                    "",
                    "end",
                    iid=row["symbol"],
                    text="ship_values",
                    open=True,
                    values=(
                        row["symbol"],
                        row["registration"]["role"],
                        row["frame"]["name"],
                        row["reactor"]["name"],
                        row["engine"]["name"],
                        module["name"],
                        mount["name"],
                        f'{row["fuel"]["current"]} / {row["fuel"]["capacity"]}',
                        f'{row["cargo"]["units"]} / {row["cargo"]["capacity"]}',
                    ),
                )
                for subrow, (module, mount) in enumerate(modules_and_mounts[1:]):
                    ship_view.insert(
                        row["symbol"],
                        "end",
                        iid=f'{row["symbol"]}#{subrow}',
                        text="modules_and_mounts",
                        values=(
                            "",
                            "",
                            "",
                            "",
                            "",
                            module["name"],
                            mount["name"],
                            "",
                            "",
                        ),
                    )

        else:
            print("Failed:", response.status_code, response.reason, response.text)

    except ConnectionError as ce:
        print("Failed:", ce)


def display_clicked_contract(*args):
        print(contract_view.index(contract_view.focus()), contract_view.focus())


def display_clicked_ship(*args):
        print(ship_view.index(ship_view.focus()), ship_view.focus())
    
def display_clicked_ship_sum(*args):
        print(ship_sum_view.index(ship_sum_view.focus()), ship_sum_view.focus())

def display_clicked_market_ship_sum(*args):
        print(market_ship_sum_view.index(market_ship_sum_view.focus()), market_ship_sum_view.focus())

def display_clicked_scan_waypoints(*args):
        print(scan_waypoints_view.index(scan_waypoints_view.focus()), scan_waypoints_view.focus())

def display_clicked_market(*args):
     print(market_view.index(market_view.focus()), market_view.focus())
     


def refresh_ship_name(*args):
        selected = ship_sum_view.focus()
        ship_name = "" 

        if selected:
                item = ship_sum_view.item(selected)
                ship_name = item["values"][0] 
                print(ship_name)
                if ship_name != "":
                        ship_name_header.config(text=ship_name)
                else:
                        ship_name_header.config(text="No Ship Selected")



        try:
                response = requests.get(
                        MY_SHIPS,
                        headers={
                                "Accept": "application/json",
                                "Authorization": f"Bearer {player_token.get()}",
                        },
                        )

                
                if response.status_code == 200:
                        result = response.json()  
                        for row in result["data"]:
                                modules_and_mounts = list(
                                        zip_longest(
                                                row["modules"], row["mounts"], fillvalue=defaultdict(str)
                        )
                        )

                                if row["symbol"] == ship_name:
                                        system = row["nav"]["systemSymbol"]
                                        waypoint = row["nav"]["waypointSymbol"]
                                        status = row["nav"]["status"]

                                        current_system.config(text=system)
                                        current_waypoint.config(text=waypoint)
                                        current_status.config(text=status)
                                        
                                        refresh_waypoints(status)
                                        break
                                else:
                                    current_system.config(text="Unknown")
                                    current_waypoint.config(text="Unknown")
                                    current_status.config(text="Unknown")     
                else:
                        print("Failed:", response.status_code, response.reason, response.text)

        except ConnectionError as ce:
                print("Failed:", ce)
        

def get_credits():
        response = requests.get(
            MY_ACCOUNT,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )
        if response.status_code == 200:
            result = response.json()

            print(f"{result['data']['credits']:n}")

            return f"{result['data']['credits']:n}"

def refresh_market_ship_name(*args):
        selected = market_ship_sum_view.focus()
        ship_name = ""

        if selected:
                item = market_ship_sum_view.item(selected)
                ship_name = item["values"][0] 
                print(ship_name)
                if ship_name != "":
                        market_ship_name_header.config(text=ship_name)
                else:
                        market_ship_name_header.config(text="No Ship Selected")



        try:
                response = requests.get(
                        MY_SHIPS,
                        headers={
                                "Accept": "application/json",
                                "Authorization": f"Bearer {player_token.get()}",
                        },
                        )

                
                if response.status_code == 200:
                        result = response.json()  
                        for row in result["data"]:
                

                                if row["symbol"] == ship_name:
                                        system = row["nav"]["systemSymbol"]
                                        waypoint = row["nav"]["waypointSymbol"]
                                        status = row["nav"]["status"]
                                        credits = get_credits()

                                        market_current_system.config(text=system)
                                        market_current_waypoint.config(text=waypoint)
                                        market_current_status.config(text=status)
                                        market_credits.config(text=credits)
                                        refresh_market(status)
                                        break
                                else:
                                    market_current_system.config(text="Unknown")
                                    market_current_waypoint.config(text="Unknown")
                                    market_current_status.config(text="Unknown")  
                                    market_credits.config(text="Unknown")    
                else:
                        print("Failed:", response.status_code, response.reason, response.text)

        except ConnectionError as ce:
                print("Failed:", ce)
        



def set_nav_waypoint(*args):
    selected = scan_waypoints_view.focus()

    if selected:
            item = scan_waypoints_view.item(selected)
            selected_waypoint_name = item["values"][1]
            if selected_waypoint_name == "":
                 selected_waypoint_name = item["values"][2]
            print(selected_waypoint_name)
            if selected_waypoint_name != "":
                    selected_waypoint.set(selected_waypoint_name)
            else:
                    selected_waypoint.set("")


def set_nav_market_waypoint(*args):
    selected = market_view.focus()

    if selected:
            item = market_view.item(selected)
            market_waypoint_name = item["values"][1]

            print(market_waypoint_name)
            if market_waypoint_name != "":
                    market_selected_waypoint.set(market_waypoint_name)
            else:
                    market_selected_waypoint.set("")
                    
                 
                 
def set_market_process(*args):
    selected = market_view.focus()
    mpt = market_purchase_type.get()
    
    print(mpt) 
    
    if mpt == "Exports":
        value = 2
        
    elif mpt == "Imports":
        value = 3
        
    elif mpt == "Exchange (Buy)" or mpt == "Exchange (Sell)":
        value = 4
    
    else:
        value = None
    

    if selected and value != None:
            item = market_view.item(selected)
            market_item = item["values"][int(value)]

            print(market_item)
            if market_item != "":
                    market_process_input.set(market_item)
            else:
                    market_process_input.set("")
                    


def double_click_scan_waypoints(*args):
    display_clicked_scan_waypoints(*args)
    set_nav_waypoint(*args)


def double_click_ship_sum(*args):
    display_clicked_ship_sum(*args)
    refresh_ship_name(*args)

def double_click_market_ship_sum(*args):
    display_clicked_market_ship_sum(*args)
    refresh_market_ship_name(*args)


def double_click_market(*args):
    display_clicked_market(*args)
    set_nav_market_waypoint(*args)
    set_market_process(*args)



def orbit():
    try:
        active_tab = tabs.index(tabs.select())
        if active_tab == 4:
            ship = market_ship_name_header.cget("text")
        else:
            ship = ship_name_header.cget("text")

        if ship == "No Ship Selected":
                return
        
        response = requests.post(
            f"https://api.spacetraders.io/v2/my/ships/{ship}/orbit",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )

        if active_tab == 4:
            refresh_market_ship_name()
        else:
            refresh_ship_name()
        print(response, "Successfully Put Ship into Orbit")
    except ConnectionError as ce:
        print("Failed:", ce)


def dock():
    try:

        active_tab = tabs.index(tabs.select())
        if active_tab == 4:
            ship = market_ship_name_header.cget("text")
        else:
            ship = ship_name_header.cget("text")

        if ship == "No Ship Selected":
                return

        response = requests.post(
            f"https://api.spacetraders.io/v2/my/ships/{ship}/dock",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )

        if active_tab == 4:
            refresh_market_ship_name()
        else:
            refresh_ship_name()

        print(response, "Successfully Docked Ship")


    except ConnectionError as ce:
        print("Failed:", ce)



def refresh_waypoints(status):


    ship = ship_name_header.cget("text")
    if ship == "No Ship Selected":
        return
    
    if ship in past_scanned_waypoints:
                result = past_scanned_waypoints[ship]
                scan_waypoints_view.delete(*scan_waypoints_view.get_children())
                for row in result["data"]["waypoints"]:
                    orbitals_and_traits = list(
                    zip_longest(
                        row["orbitals"], row["traits"], fillvalue=defaultdict(str)
                    )
                )


                    scan_waypoints_view.insert(
                        "",
                        "end",
                        iid=row["symbol"],
                        text="ship_values",
                        open=True,
                        values=(
                            row["type"],
                            row["symbol"],
                            "",
                            "",
                        ),
                    )
                    for subrow, (orbital, traits) in enumerate(orbitals_and_traits[0:]):
                        scan_waypoints_view.insert(
                            row["symbol"],
                            "end",
                            iid=f'{row["symbol"]}#{subrow}',
                            text="orbitals",
                            values=(
                                "",
                                "",
                                orbital["symbol"],
                                traits["symbol"],

                            ),
                        )

    elif status == "IN_ORBIT":

        try:
            response = requests.post(
                f"https://api.spacetraders.io/v2/my/ships/{ship}/scan/waypoints",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {player_token.get()}",
                },
            )


            #print(response.status_code)

            if response.status_code == 201:
                result = response.json()
                past_scanned_waypoints[ship] = result
                refresh_waypoints(status)
                

            elif response.status_code == 409:
                    result = response.json()
                    cooldown = result["error"]["data"]["cooldown"]["remainingSeconds"]
                    print(cooldown)
            else:
                print("Failed:", response.status_code, response.reason, response.text)

        except ConnectionError as ce:
            print("Failed:", ce)
    else:
        orbit()
        
        
        

def refresh_market(status):


    ship = market_ship_name_header.cget("text")
    if ship == "No Ship Selected":
        return
    
    if ship in past_scanned_waypoints:
                result = past_scanned_waypoints[ship]
                market_view.delete(*market_view.get_children())
                for row in result["data"]["waypoints"]:
                    traits = row["traits"]
                    
                    market_trait = False
                    for tag in traits:
                        if tag["symbol"] == "MARKETPLACE":
                            market_trait = True

                    if market_trait:

                        waypoint_symbol = row["symbol"]

                        if waypoint_symbol not in past_markets:
                            past_markets[waypoint_symbol] = get_market(
                                row["symbol"], row["systemSymbol"]
                            )

                        exports, imports, exchange = past_markets[waypoint_symbol]

                        shop = list(
                             zip_longest(exports, imports, exchange, fillvalue="")
                             )
                        

                        market_view.insert(
                            "",
                            "end",
                            iid=row["symbol"],
                            text="ship_values",
                            open=True,
                            values=(
                                row["type"],
                                row["symbol"],
                                "",
                                "",
                                "",
                            ),
                        )
                        for subrow, (exports, imports, exchange) in enumerate(shop[0:]):
                            market_view.insert(
                                row["symbol"],
                                "end",
                                iid=f'{row["symbol"]}#{subrow}',
                                text="marketplaces",
                                values=(
                                    "",
                                    "",
                                    exports,
                                    imports,
                                    exchange,

                                ),
                            )

    elif status == "IN_ORBIT":

        try:
            response = requests.post(
                f"https://api.spacetraders.io/v2/my/ships/{ship}/scan/waypoints",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {player_token.get()}",
                },
            )


            #print(response.status_code)

            if response.status_code == 201:
                result = response.json()
                past_scanned_waypoints[ship] = result
                refresh_market(status)
                

            elif response.status_code == 409:
                    result = response.json()
                    market_cooldown = result["error"]["data"]["cooldown"]["remainingSeconds"]
                    print(market_cooldown)
            else:
                print("Failed:", response.status_code, response.reason, response.text)

        except ConnectionError as ce:
            print("Failed:", ce)
    else:
        orbit()


    
def get_market(waypoint, system):
    try:
        if system == "" or waypoint == "":
             return [], [], []

        response = requests.get(
            f"https://api.spacetraders.io/v2/systems/{system}/waypoints/{waypoint}/market",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )

        if response.status_code == 200:
            result = response.json()

            if result["data"]:

                
            
                exports_temp = []
                imports_temp = []
                exchange_temp = []

                exports = result["data"]["exports"]

                for i in range(len(exports)):
                    exports_temp.append(exports[i]["symbol"])

                imports = result["data"]["imports"]

                for i in range(len(imports)):
                    imports_temp.append(imports[i]["symbol"])

                exchange = result["data"]["exchange"]

                for i in range(len(exchange)):
                    exchange_temp.append(exchange[i]["symbol"])

                print(exports_temp)
                print(imports_temp)
                print(exchange_temp)
                     
                return exports_temp, imports_temp, exchange_temp
            
            return [], [], []
        
        return [], [], []
        
    except ConnectionError as ce:
        print("Failed:", ce)
        return [], [], []
        



def navigate(loco):
    try:
        
        if loco == "market":
            waypoint = market_navigate_entry.get()
        else:
            waypoint = navigate_entry.get()

        if waypoint == "":
                return
        
        if loco == "market":
                    ship = market_ship_name_header.cget("text")

        elif loco == "ships":
                    ship = ship_name_header.cget("text")

        if ship == "No Ship Selected":
                print("No Ship Selected")
                return

        response = requests.post(
            f"https://api.spacetraders.io/v2/my/ships/{ship}/navigate",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
            json={
                 "waypointSymbol": waypoint
            }
        )

        #if response.status_code == 400:
        #     result = response.json()
        #     if result["error"]["code"] == 4214:
        #        transit_time_left = str(result["error"]["data"]["secondsToArrival"])
        #        return transit_time_left
        
        print(response, "Successfully Navigated Ship to waypoint: ", waypoint)
        if loco == "market":
            refresh_market_ship_name()
        else:
            refresh_ship_name()
    except ConnectionError as ce:
        print("Failed:", ce)



def nav_info(loco):
    try:
        
        if loco == "market":
                    ship = market_ship_name_header.cget("text")

        elif loco == "ships":
                    ship = ship_name_header.cget("text")

        if ship == "No Ship Selected":
                print("No Ship Selected")
                return

        response = requests.get(
            f"https://api.spacetraders.io/v2/my/ships/{ship}/nav",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )
        
        if response.status_code == 200:
            result = response.json()
            if result["data"]["status"] == "IN_TRANSIT":
                current_time = datetime.now(timezone.utc)
                arrival = result["data"]["route"]["arrival"]
                arrival = datetime.fromisoformat(arrival)
                difference = arrival - current_time
                seconds_remaining = int(difference.total_seconds())

                print(seconds_remaining)

                time_left = str(seconds_remaining) + " Seconds Left Till Arrival"
                
                if loco == "market":
                    market_transit_time.config(text=time_left)
                else:
                    transit_time.config(text=time_left)
            else:
                if loco == "market":
                    market_transit_time.config(text="")
                else:
                    transit_time.config(text="")





    except ConnectionError as ce:
        print("Failed:", ce)

    global nav_info_job
    if nav_info_job is not None:
        root.after_cancel(nav_info_job)
    nav_info_job = root.after(1000, lambda: nav_info(loco))



def refresh_leaderboard(*args):
    try:
        response = requests.get(
            API_STATUS,
            params={"token": player_token.get()},
        )
        if response.status_code == 200:
            result = response.json()
            credits_leaderboard_view.delete(*credits_leaderboard_view.get_children())
            for rank, row in enumerate(result["leaderboards"]["mostCredits"]):
                credits_leaderboard_view.insert(
                    "",
                    "end",
                    text="values",
                    values=(rank + 1, row["agentSymbol"], f"{row['credits']:n}"),
                )

            charts_leaderboard_view.delete(*charts_leaderboard_view.get_children())
            for rank, row in enumerate(result["leaderboards"]["mostSubmittedCharts"]):
                charts_leaderboard_view.insert(
                    "",
                    "end",
                    text="values",
                    values=(rank + 1, row["agentSymbol"], f"{row['chartCount']:n}"),
                )

        else:
            print("Failed:", response.status_code, response.reason, response.text)

    except ConnectionError as ce:
        print("Failed:", ce)


def navigate_button_click(loco):
    global nav_info_job
    if nav_info_job is not None:
        root.after_cancel(nav_info_job)
        nav_info_job = None
    navigate(loco)
    nav_info(loco)



def get_cargo(ship):
    try:
        if ship == "":
                return []

        response = requests.get(
            f"https://api.spacetraders.io/v2/my/ships/{ship}/cargo",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )

        if response.status_code == 200:
            result = response.json()

            if result["data"]["inventory"]:
                return result["data"]["inventory"]
            
            return []
        
    except ConnectionError as ce:
        print("Failed:", ce)
        return []
    return []
    
    



def refresh_ships(*args):
    try:

        
        response = requests.get(
            MY_SHIPS,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )

        
        if response.status_code == 200:
            error_message.set(" ")
            result = response.json()
            ship_sum_view.delete(*ship_sum_view.get_children())
            for row in result["data"]:
                modules_and_mounts = list(
                    zip_longest(
                        row["modules"], row["mounts"], get_cargo(row["symbol"]), fillvalue=defaultdict(str)
                    )
                )
                
                

                ship_sum_view.insert(
                    "",
                    "end",
                    iid=row["symbol"],
                    text="ship_values",
                    open=True,
                    values=(
                        row["symbol"],
                        row["registration"]["role"],
                        row["frame"]["name"],
                        row["reactor"]["name"],
                        row["engine"]["name"],
                        "",
                        "",
                        f'{row["fuel"]["current"]} / {row["fuel"]["capacity"]}',
                        f'{row["cargo"]["units"]} / {row["cargo"]["capacity"]}',
                        "", 
                        "",
                    ),
                )
                for subrow, (module, mount, inventory) in enumerate(modules_and_mounts[0:]):
                    ship_sum_view.insert(
                        row["symbol"],
                        "end",
                        iid=f'{row["symbol"]}#{subrow}',
                        text="modules_and_mounts",
                        values=(
                            "",
                            "",
                            "",
                            "",
                            "",
                            module["name"],
                            mount["name"],
                            "",
                            "",
                            inventory["name"],
                            inventory["units"],                            
                        ),
                    )

        else:
            print("Failed:", response.status_code, response.reason, response.text)
        
    except ConnectionError as ce:
        print("Failed:", ce)
    
    
def refresh_marketplace(*args):
    try:

        
        response = requests.get(
            MY_SHIPS,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
        )

        
        if response.status_code == 200:
            market_error_message.set(" ")
            result = response.json()
            market_ship_sum_view.delete(*market_ship_sum_view.get_children())
            for row in result["data"]:
                modules_and_mounts = list(
                    zip_longest(
                        row["modules"], row["mounts"], get_cargo(row["symbol"]), fillvalue=defaultdict(str)
                    )
                )
                
                if len(modules_and_mounts) > 0:
                    module, mount, inventory = modules_and_mounts[0]

                

                market_ship_sum_view.insert(
                    "",
                    "end",
                    iid=row["symbol"],
                    text="ship_values",
                    open=True,
                    values=(
                        row["symbol"],
                        row["registration"]["role"],
                        row["frame"]["name"],
                        row["reactor"]["name"],
                        row["engine"]["name"],
                        "",
                        "",
                        f'{row["fuel"]["current"]} / {row["fuel"]["capacity"]}',
                        f'{row["cargo"]["units"]} / {row["cargo"]["capacity"]}',
                        "", 
                        "",
                    ),
                )
                for subrow, (module, mount, inventory) in enumerate(modules_and_mounts[0:]):
                    market_ship_sum_view.insert(
                        row["symbol"],
                        "end",
                        iid=f'{row["symbol"]}#{subrow}',
                        text="modules_and_mounts",
                        values=(
                            "",
                            "",
                            "",
                            "",
                            "",
                            module["name"],
                            mount["name"],
                            "",
                            "",
                            inventory["name"],
                            inventory["units"],                            
                        ),
                    )

        else:
            print("Failed:", response.status_code, response.reason, response.text)
        
    except ConnectionError as ce:
        print("Failed:", ce)



def refuel():
        ship = ship_name_header.cget("text")
        if ship == "No Ship Selected":
                return
            
        
        check_box = bool(from_cargo.get())
        
        
        refuel_string = refuel_input.get()
        if not refuel_string:
            return
        try:
            num = int(refuel_string)
        except ValueError:
            return

                    
        dock()

        
        response = requests.post(
            f"https://api.spacetraders.io/v2/my/ships/{ship}/refuel",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            },
            json={
                  "units": num,
                  "fromCargo": check_box
                }
        )

        #result = response.json()
        if response.status_code == 200:
             refresh_ships()


        print(response)
        #print(result)




def extract():
        ship = ship_name_header.cget("text")
        if ship == "No Ship Selected":
                return

        
    
        
        
        response = requests.post(
            f"https://api.spacetraders.io/v2/my/ships/{ship}/extract",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {player_token.get()}",
            }
        )

        result = response.json()
        if response.status_code == 201:
             refresh_ships()
             error_message.set(" ")
        elif response.status_code == 409:
             print(result["error"]["message"])
             error_message.set(result["error"]["message"])


        
        
        print(response)
        print(result)
        
        
          
        
def proceed_market_action():
    selected = market_view.focus()

    ship = market_ship_name_header.cget("text")
    if ship == "No Ship Selected":
        return
    
    mpt = market_purchase_type.get()
    
    print(mpt) 
    
    if mpt == "Exports":
        value = 2
        
    elif mpt == "Imports":
        value = 3
        
    elif mpt == "Exchange (Buy)":
        value = 4

    elif mpt == "Exchange (Sell)":
        value = 5
    
    else:
        value = None
    

    if selected and value != None:
            market_item = market_process_input.get()

            print(market_item)
            
            
            units_string = market_units.get()

            if not units_string:
                return
            try:
                units = int(units_string)
            except ValueError:
                return

            if units and market_item:
                dock()

                if value == 3 or value == 5:
                    response = requests.post(
                        f"https://api.spacetraders.io/v2/my/ships/{ship}/sell",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {player_token.get()}"
                        },

                        json={
                            "symbol": market_item,
                            "units": units
                        }
                                )
                    
                else:
                                       
                    response = requests.post(
                        f"https://api.spacetraders.io/v2/my/ships/{ship}/purchase",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {player_token.get()}"
                        },

                        json={
                            "symbol": market_item,
                            "units": units
                        }
                                )
                
                if response:
                    result = response.json()
                    if response.status_code == 201 or response.status_code == 200:
                        refresh_marketplace()
                        refresh_market_ship_name()


                    print(response)
                    print(result)
        
###
# Root window, with app title
#
root = tk.Tk()
root.title("Io Space Trading")

# Main themed frame, for all other widgets to rest upon
main = ttk.Frame(root, padding="3 3 12 12")
main.grid(sticky=tk.NSEW)

root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

# Tabbed widget for rest of the app to run in
tabs = ttk.Notebook(main)
tabs.grid(sticky=tk.NSEW)
tabs.bind("<<NotebookTabChanged>>", refresh_tabs)

main.columnconfigure(0, weight=1)
main.rowconfigure(0, weight=1)

# setup the three main tabs
welcome = ttk.Frame(tabs)
summary = ttk.Frame(tabs)
leaderboard = ttk.Frame(tabs)
ships = ttk.Frame(tabs)
marketplace = ttk.Frame(tabs)

tabs.add(welcome, text="Welcome")
tabs.add(summary, text="Summary")
tabs.add(leaderboard, text="Leaderboard")
tabs.add(ships, text="Ships")
tabs.add(marketplace, text="Marketplace")


tabs.tab(1, state=tk.DISABLED)
tabs.tab(2, state=tk.DISABLED)
tabs.tab(3, state=tk.DISABLED)
tabs.tab(4, state=tk.DISABLED)



###
# agent registration/login tab
#

welcome_frame = ttk.Frame(welcome)
welcome_frame.grid(row=0, column=0, columnspan=2, sticky=tk.NSEW)

# left hand frame will check/register new agents and return/store the UUID
register = ttk.LabelFrame(welcome_frame, text="Register", relief="groove", padding=5)
register.grid(sticky=tk.NSEW)

# widgets required on the left are a label, an entry, a dropdown, and a button
agent_name = tk.StringVar()
agent_faction = tk.StringVar()
ttk.Label(
    register, text="Enter a new agent name\nto start a new account", anchor=tk.CENTER
).grid(sticky=tk.EW)
faction_combobox = ttk.Combobox(
    register, textvariable=agent_faction, postcommand=generate_faction_combobox
)
faction_combobox.grid(row=1, column=0, sticky=tk.EW)
ttk.Entry(register, textvariable=agent_name).grid(row=2, column=0, sticky=tk.EW)
ttk.Button(register, text="Register new agent", command=register_agent).grid(
    row=3, column=0, columnspan=2, sticky=tk.EW
)

register.columnconfigure(0, weight=1)
register.rowconfigure(0, weight=1)

ttk.Label(welcome_frame, text="or", padding=10, anchor=tk.CENTER).grid(
    row=0, column=1, sticky=tk.EW
)

# right hand frame will allow to choose from known players and/or paste in existing
# UUID to login and play as that agent
login = ttk.LabelFrame(welcome_frame, text="Login", relief=tk.GROOVE, padding=5)
login.grid(row=0, column=2, sticky=tk.NSEW)

# widgets required on the right are a dropdown, and a button
player_login = tk.StringVar()
player_token = (
    tk.StringVar()
)  # going to use this to remember the currently logged in agent
ttk.Label(login, text="Choose the agent to play as\nor paste an existing id").grid(
    sticky=tk.EW
)
id_login = ttk.Combobox(
    login, textvariable=player_login, postcommand=generate_login_combobox
)
id_login.grid(row=1, column=0, sticky=tk.EW)
ttk.Button(login, text="Login agent", command=login_agent).grid(
    row=2, column=0, columnspan=2, sticky=tk.EW
)

login.columnconfigure(0, weight=1)
login.rowconfigure(0, weight=1)

welcome_frame.columnconfigure(0, weight=1)
welcome_frame.columnconfigure(2, weight=1)
welcome_frame.rowconfigure(0, weight=1)

welcome.columnconfigure(0, weight=1)
welcome.rowconfigure(0, weight=1)







###
# summary tab
#

player_summary = ttk.LabelFrame(summary, text="Agent", relief=tk.GROOVE, padding=5)

player_faction = tk.StringVar()
player_worth = tk.StringVar()

ttk.Label(player_summary, textvariable=player_login, anchor=tk.CENTER).grid(
    columnspan=2, sticky=tk.EW
)
ttk.Label(player_summary, text="Faction:").grid(row=1, column=0, sticky=tk.W)
ttk.Label(player_summary, textvariable=player_faction, anchor=tk.CENTER).grid(
    row=1, column=1, sticky=tk.EW
)
ttk.Label(player_summary, text="Credits:").grid(row=2, column=0, sticky=tk.W)
ttk.Label(player_summary, textvariable=player_worth, anchor=tk.CENTER).grid(
    row=2, column=1, sticky=tk.EW
)
ttk.Button(player_summary, text="Logout", command=logout_agent).grid(
    row=3, column=0, columnspan=2, sticky=tk.EW
)

player_summary.columnconfigure(0, weight=1)

contract_summary = ttk.LabelFrame(
    summary, text="Contracts", relief=tk.GROOVE, padding=5
)

contract_view = ttk.Treeview(
    contract_summary,
    height=3,
    columns=("Faction", "Type", "Deadline", "Goods", "Destination", "Owing"),
    show="headings",
)
contract_view.column("Faction", anchor=tk.W, width=20)
contract_view.column("Type", anchor=tk.W, width=20)
contract_view.column("Deadline", anchor=tk.W, width=20)
contract_view.column("Goods", anchor=tk.W, width=30)
contract_view.column("Destination", anchor=tk.W, width=20)
contract_view.column("Owing", anchor=tk.E, width=20)
contract_view.heading("#1", text="Faction")
contract_view.heading("#2", text="Type")
contract_view.heading("#3", text="Deadline")
contract_view.heading("#4", text="Goods")
contract_view.heading("#5", text="Destination")
contract_view.heading("#6", text="Owing")
contract_view.grid(sticky=tk.NSEW)
contract_scroll = ttk.Scrollbar(
    contract_summary, orient=tk.VERTICAL, command=contract_view.yview
)
contract_scroll.grid(column=1, row=0, sticky=tk.NS)
contract_view.config(yscrollcommand=contract_scroll.set)
contract_view.bind("<Double-1>", display_clicked_contract)

contract_summary.columnconfigure(0, weight=1)
contract_summary.rowconfigure(0, weight=1)

ship_summary = ttk.LabelFrame(summary, text="Ships", relief=tk.GROOVE, padding=5)
ship_view = ttk.Treeview(
    ship_summary,
    height=3,
    columns=(
        "Registration",
        "Role",
        "Frame",
        "Reactor",
        "Engine",
        "Modules",
        "Mounts",
        "Fuel",
        "Cargo",
    ),
    show="headings",
)
ship_view.column("Registration", anchor=tk.W, width=30)
ship_view.column("Role", anchor=tk.W, width=30)
ship_view.column("Frame", anchor=tk.W, width=30)
ship_view.column("Reactor", anchor=tk.W, width=30)
ship_view.column("Engine", anchor=tk.W, width=30)
ship_view.column("Modules", anchor=tk.W, width=30)
ship_view.column("Mounts", anchor=tk.W, width=30)
ship_view.column("Fuel", anchor=tk.E, width=20)
ship_view.column("Cargo", anchor=tk.E, width=20)
ship_view.heading("#1", text="Registration")
ship_view.heading("#2", text="Role")
ship_view.heading("#3", text="Frame")
ship_view.heading("#4", text="Reactor")
ship_view.heading("#5", text="Engine")
ship_view.heading("#6", text="Modules")
ship_view.heading("#7", text="Mounts")
ship_view.heading("#8", text="Fuel")
ship_view.heading("#9", text="Cargo")
ship_view.grid(sticky=tk.NSEW)
ship_scroll = ttk.Scrollbar(ship_summary, orient=tk.VERTICAL, command=ship_view.yview)
ship_scroll.grid(column=1, row=0, sticky=tk.NS)
ship_view.config(yscrollcommand=ship_scroll.set)
ship_view.bind("<Double-1>", display_clicked_ship)

ship_summary.columnconfigure(0, weight=1)
ship_summary.rowconfigure(0, weight=1)


player_summary.grid(row=0, column=0, sticky=tk.NSEW)
contract_summary.grid(row=0, column=1, sticky=tk.NSEW)
ship_summary.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW)

summary.columnconfigure(0, weight=1)
summary.columnconfigure(1, weight=3)
summary.rowconfigure(0, weight=2)
summary.rowconfigure(1, weight=3)











###
# leaderboard tab
#

credits_leaderboard_view = ttk.Treeview(
    leaderboard, height=6, columns=("Rank", "Agent", "Credits"), show="headings"
)
credits_leaderboard_view.column("Rank", anchor=tk.CENTER, width=10)
credits_leaderboard_view.column("Agent", anchor=tk.W, width=100)
credits_leaderboard_view.column("Credits", anchor=tk.E, width=100)
credits_leaderboard_view.heading("#1", text="Rank")
credits_leaderboard_view.heading("#2", text="Agent")
credits_leaderboard_view.heading("#3", text="Credits")
credits_leaderboard_view.grid(sticky=tk.NSEW)
credits_scroll = ttk.Scrollbar(
    leaderboard, orient=tk.VERTICAL, command=credits_leaderboard_view.yview
)
credits_scroll.grid(column=1, row=0, sticky=tk.NS)
credits_leaderboard_view.config(yscrollcommand=credits_scroll.set)

charts_leaderboard_view = ttk.Treeview(
    leaderboard, height=6, columns=("Rank", "Agent", "Chart Count"), show="headings"
)
charts_leaderboard_view.column("Rank", anchor=tk.CENTER, width=10)
charts_leaderboard_view.column("Agent", anchor=tk.W, width=100)
charts_leaderboard_view.column("Chart Count", anchor=tk.E, width=100)
charts_leaderboard_view.heading("#1", text="Rank")
charts_leaderboard_view.heading("#2", text="Agent")
charts_leaderboard_view.heading("#3", text="Chart Count")
charts_leaderboard_view.grid(sticky=tk.NSEW)
charts_scroll = ttk.Scrollbar(
    leaderboard, orient=tk.VERTICAL, command=charts_leaderboard_view.yview
)
charts_scroll.grid(column=1, row=1, sticky=tk.NS)
charts_leaderboard_view.config(yscrollcommand=charts_scroll.set)

refresh = ttk.Button(leaderboard, text="Refresh", command=refresh_leaderboard)
refresh.grid(column=0, row=2, sticky=tk.EW)

leaderboard.columnconfigure(0, weight=1)
leaderboard.rowconfigure((0, 1), weight=1)











###
# ships tab
#


#This displays the ship data in a tree view at the bottom of the page allowing the user to view summarised info about all the ships they own and then double click a desired ship to update the rest of the page with more detailed and specified information
ship_sum = ttk.LabelFrame(ships, text="Ships", relief=tk.GROOVE, padding=5)
ship_sum_view = ttk.Treeview(
    ship_sum,
    height=3,
    columns=(
        "Registration",
        "Role",
        "Frame",
        "Reactor",
        "Engine",
        "Modules",
        "Mounts",
        "Fuel",
        "Cargo",
        "Inventory",
        "Units",
    ),
    show="headings",
)
ship_sum_view.column("Registration", anchor=tk.W, width=30)
ship_sum_view.column("Role", anchor=tk.W, width=30)
ship_sum_view.column("Frame", anchor=tk.W, width=30)
ship_sum_view.column("Reactor", anchor=tk.W, width=30)
ship_sum_view.column("Engine", anchor=tk.W, width=30)
ship_sum_view.column("Modules", anchor=tk.W, width=30)
ship_sum_view.column("Mounts", anchor=tk.W, width=30)
ship_sum_view.column("Fuel", anchor=tk.E, width=20)
ship_sum_view.column("Cargo", anchor=tk.E, width=20)
ship_sum_view.column("Inventory", anchor=tk.E, width=20)
ship_sum_view.column("Units", anchor=tk.E, width=20)
ship_sum_view.heading("#1", text="Registration")
ship_sum_view.heading("#2", text="Role")
ship_sum_view.heading("#3", text="Frame")
ship_sum_view.heading("#4", text="Reactor")
ship_sum_view.heading("#5", text="Engine")
ship_sum_view.heading("#6", text="Modules")
ship_sum_view.heading("#7", text="Mounts")
ship_sum_view.heading("#8", text="Fuel")
ship_sum_view.heading("#9", text="Cargo")
ship_sum_view.heading("#10", text="Inventory")
ship_sum_view.heading("#11", text="Units")
ship_sum_view.grid(sticky=tk.NSEW)
ship_sum_scroll = ttk.Scrollbar(ship_sum, orient=tk.VERTICAL, command=ship_sum_view.yview)
ship_sum_scroll.grid(column=1, row=0, sticky=tk.NS)
ship_sum_view.config(yscrollcommand=ship_sum_scroll.set)
ship_sum_view.bind("<Double-1>", double_click_ship_sum)











#Current Location section

current_location = ttk.LabelFrame(ships, text="Current Location", relief=tk.GROOVE, padding=5)



#Dynamic ship header based on selected ship in table below

ship_name_header = ttk.Label(current_location, text="No Ship Selected", anchor=tk.CENTER)

ship_name_header.grid(columnspan=2, sticky=tk.EW)

#Useful (yet slightly under used) Dynamic Error message label
error_message = tk.StringVar()

error_message_display = ttk.Label(current_location, textvariable = error_message, anchor=tk.CENTER)
error_message_display.grid(row=0, column=1, sticky=tk.EW)

ttk.Label(current_location, text="Current System:").grid(row=1, column=0, sticky=tk.W)

current_system = ttk.Label(current_location, text = "Unknown", anchor=tk.CENTER)
current_system.grid(row=1, column=1, sticky=tk.EW)

ttk.Label(current_location, text="Current Waypoint:").grid(row=2, column=0, sticky=tk.W)

current_waypoint = ttk.Label(current_location, text = "Unknown", anchor=tk.CENTER)
current_waypoint.grid(row=2, column=1, sticky=tk.EW)

ttk.Label(current_location, text="Current Status:").grid(row=3, column=0, sticky=tk.W)

current_status = ttk.Label(current_location, text = "Unknown", anchor=tk.CENTER)
current_status.grid(row=3, column=1, sticky=tk.EW)



orbit_button = ttk.Button(current_location, text="Orbit", command=orbit)    #Orbit button
orbit_button.grid(column=2, row=3, sticky=tk.EW)


dock_button = ttk.Button(current_location, text="Dock", command=dock)       #Dock button
dock_button.grid(column=3, row=3, sticky=tk.EW)


filler_1 = ttk.Label(current_location, text = "", anchor=tk.CENTER)
filler_1.grid(row=4, column=1, sticky=tk.EW)


#Dynamic navigation textbox
#Works by taking the selected row on the scan waypoints table and retrieving the waypoint for that row and autofilling it on the textbox allowing the user to very easily travel to a listed waypoint without the extra hassle of typing the waypoint out 
#double click feature assists with the desired essense of this program to make it a more user friendly game

selected_waypoint = tk.StringVar()


navigate_entry = ttk.Entry(current_location, textvariable=selected_waypoint)
navigate_entry.grid(column=0, row=5, sticky=tk.EW)


navigate_button = ttk.Button(current_location, text="Navigate", command=lambda: navigate_button_click("ships"))
navigate_button.grid(column=1, row=5, sticky=tk.EW)



#Display the transit time left for the ship to reach a location
transit_time = ttk.Label(current_location, text = " ", anchor=tk.CENTER)
transit_time.grid(row=5, column=2, sticky=tk.EW)

refuel_input = tk.StringVar()

refuel_entry = ttk.Entry(current_location, textvariable=refuel_input)
refuel_entry.grid(column=0, row=7, columnspan=1, sticky=tk.EW)

refuel_button = ttk.Button(current_location, text="Refuel", command=refuel)
refuel_button.grid(column=1, row=7, columnspan=1, sticky=tk.EW)


from_cargo = tk.IntVar()

refuel_check_button = Checkbutton(current_location, text = "Refuel From Cargo", variable = from_cargo, onvalue = 1, offvalue = 0, height = 2, width = 10)
refuel_check_button.grid(column=2, row=7, columnspan=4, sticky=tk.EW) 


extract_button = ttk.Button(current_location, text="Extract", command=extract)
extract_button.grid(column=1, row=8, sticky=tk.EW)



#Display Available waypoints
scan_waypoints = ttk.LabelFrame(ships, text="Scanned Waypoints", relief=tk.GROOVE, padding=5)
scan_waypoints_view = ttk.Treeview(
    scan_waypoints,
    height=3,
    columns=(
        "Type",
        "Waypoint",
        "Orbitals",
        "Traits",
    ),
    show="headings",
)
scan_waypoints_view.column("Type", anchor=tk.W, width=30)
scan_waypoints_view.column("Waypoint", anchor=tk.W, width=30)
scan_waypoints_view.column("Orbitals", anchor=tk.W, width=30)
scan_waypoints_view.column("Traits", anchor=tk.W, width=30)

scan_waypoints_view.heading("#1", text="Type")
scan_waypoints_view.heading("#2", text="Waypoint")
scan_waypoints_view.heading("#3", text="Orbitals")
scan_waypoints_view.heading("#4", text="Traits")

scan_waypoints_view.grid(sticky=tk.NSEW)
scan_waypoints_scroll = ttk.Scrollbar(scan_waypoints, orient=tk.VERTICAL, command=scan_waypoints_view.yview)
scan_waypoints_scroll.grid(column=1, row=0, sticky=tk.NS)
scan_waypoints_view.config(yscrollcommand=scan_waypoints_scroll.set)
scan_waypoints_view.bind("<Double-1>", double_click_scan_waypoints)





#Formats Ship display


scan_waypoints.grid(row=0, column=1, columnspan=2, sticky=tk.NSEW)
scan_waypoints.columnconfigure(0, weight=1)
scan_waypoints.rowconfigure(0, weight=1)


current_location.columnconfigure(0, weight=1)
current_location.grid(row=0, column=0, columnspan=1, sticky=tk.NSEW)


ship_sum.grid(row=1, column=0, columnspan=5, sticky=tk.NSEW)
ship_sum.columnconfigure(0, weight=1)
ship_sum.rowconfigure(0, weight=1)





ships.columnconfigure(0, weight=1)
ships.columnconfigure(1, weight=3)
ships.rowconfigure(0, weight=2)
ships.rowconfigure(1, weight=3)







#Marketplace tab
#Displays a summary of all the users ships and afacilitates the double click method used early that also updates this tabs features that allow the user to gain more insightful and ship speciifc data on demand
market_ship_sum = ttk.LabelFrame(marketplace, text="Ships", relief=tk.GROOVE, padding=5)
market_ship_sum_view = ttk.Treeview(
    market_ship_sum,
    height=3,
    columns=(
        "Registration",
        "Role",
        "Frame",
        "Reactor",
        "Engine",
        "Modules",
        "Mounts",
        "Fuel",
        "Cargo",
        "Inventory",
        "Units",
    ),
    show="headings",
)
market_ship_sum_view.column("Registration", anchor=tk.W, width=30)
market_ship_sum_view.column("Role", anchor=tk.W, width=30)
market_ship_sum_view.column("Frame", anchor=tk.W, width=30)
market_ship_sum_view.column("Reactor", anchor=tk.W, width=30)
market_ship_sum_view.column("Engine", anchor=tk.W, width=30)
market_ship_sum_view.column("Modules", anchor=tk.W, width=30)
market_ship_sum_view.column("Mounts", anchor=tk.W, width=30)
market_ship_sum_view.column("Fuel", anchor=tk.E, width=20)
market_ship_sum_view.column("Cargo", anchor=tk.E, width=20)
market_ship_sum_view.column("Inventory", anchor=tk.E, width=20)
market_ship_sum_view.column("Units", anchor=tk.E, width=20)
market_ship_sum_view.heading("#1", text="Registration")
market_ship_sum_view.heading("#2", text="Role")
market_ship_sum_view.heading("#3", text="Frame")
market_ship_sum_view.heading("#4", text="Reactor")
market_ship_sum_view.heading("#5", text="Engine")
market_ship_sum_view.heading("#6", text="Modules")
market_ship_sum_view.heading("#7", text="Mounts")
market_ship_sum_view.heading("#8", text="Fuel")
market_ship_sum_view.heading("#9", text="Cargo")
market_ship_sum_view.heading("#10", text="Inventory")
market_ship_sum_view.heading("#11", text="Units")
market_ship_sum_view.grid(sticky=tk.NSEW)
market_ship_sum_scroll = ttk.Scrollbar(market_ship_sum, orient=tk.VERTICAL, command=market_ship_sum_view.yview)
market_ship_sum_scroll.grid(column=1, row=0, sticky=tk.NS)
market_ship_sum_view.config(yscrollcommand=market_ship_sum_scroll.set)
market_ship_sum_view.bind("<Double-1>", double_click_market_ship_sum)






#Filters through the waypoints scanned from the ships tab and then displays only those that have the market place trait, which it then uses to get info on the marketplace at the location to provide the user with all the info they need about nearby marketplaces
#Then allows double click of market place parent in treeview to allow the user to autofill the waypoint into the read only naviagtion system on the marketplace tab restricting the user to only travel to market places when on the marketplace tab to reduce chance of errors
market = ttk.LabelFrame(marketplace, text="Nearby Marketplaces", relief=tk.GROOVE, padding=5)
market_view = ttk.Treeview(
    market,
    height=3,
    columns=(
        "Type",
        "Waypoint",
        "Exports",
        "Imports",
        "Exchange"
    ),
    show="headings",
)
market_view.column("Type", anchor=tk.W, width=30)
market_view.column("Waypoint", anchor=tk.W, width=30)
market_view.column("Exports", anchor=tk.W, width=30)
market_view.column("Imports", anchor=tk.W, width=30)
market_view.column("Exchange", anchor=tk.W, width=30)


market_view.heading("#1", text="Type")
market_view.heading("#2", text="Waypoint")
market_view.heading("#3", text="Exports")
market_view.heading("#4", text="Imports")
market_view.heading("#5", text="Exchange")

market_view.grid(sticky=tk.NSEW)
market_scroll = ttk.Scrollbar(market, orient=tk.VERTICAL, command=market_view.yview)
market_scroll.grid(column=1, row=0, sticky=tk.NS)
market_view.config(yscrollcommand=market_scroll.set)
market_view.bind("<Double-1>", double_click_market)






#Formats Ship display


market.grid(row=0, column=1, columnspan=2, sticky=tk.NSEW)
market.columnconfigure(0, weight=1)
market.rowconfigure(0, weight=1)





#Current Location section

market_current_location = ttk.LabelFrame(marketplace, text="Current Location", relief=tk.GROOVE, padding=5)



#Dynamic ship header based on selected ship in table below

market_ship_name_header = ttk.Label(market_current_location, text="No Ship Selected", anchor=tk.CENTER)

market_ship_name_header.grid(columnspan=2, sticky=tk.EW)


market_error_message = tk.StringVar()

market_error_message_display = ttk.Label(market_current_location, textvariable = market_error_message, anchor=tk.CENTER)
market_error_message_display.grid(row=0, column=1, sticky=tk.EW)

ttk.Label(market_current_location, text="Current System:").grid(row=1, column=0, sticky=tk.W)

market_current_system = ttk.Label(market_current_location, text = "Unknown", anchor=tk.CENTER)
market_current_system.grid(row=1, column=1, sticky=tk.EW)

ttk.Label(market_current_location, text="Current Waypoint:").grid(row=2, column=0, sticky=tk.W)

market_current_waypoint = ttk.Label(market_current_location, text = "Unknown", anchor=tk.CENTER)
market_current_waypoint.grid(row=2, column=1, sticky=tk.EW)

ttk.Label(market_current_location, text="Current Status:").grid(row=3, column=0, sticky=tk.W)

market_current_status = ttk.Label(market_current_location, text = "Unknown", anchor=tk.CENTER)
market_current_status.grid(row=3, column=1, sticky=tk.EW)



market_orbit_button = ttk.Button(market_current_location, text="Orbit", command=orbit)
market_orbit_button.grid(column=2, row=3, sticky=tk.EW)


market_dock_button = ttk.Button(market_current_location, text="Dock", command=dock)
market_dock_button.grid(column=3, row=3, sticky=tk.EW)

ttk.Label(market_current_location, text="Credits:").grid(row=4, column=0, sticky=tk.W)

market_credits = ttk.Label(market_current_location, text = "Unknown", anchor=tk.CENTER)
market_credits.grid(row=4, column=1, sticky=tk.EW)




market_selected_waypoint = tk.StringVar()


market_navigate_entry = ttk.Entry(market_current_location, textvariable=market_selected_waypoint)
market_navigate_entry.grid(column=0, row=5, sticky=tk.EW)


market_navigate_button = ttk.Button(market_current_location, text="Navigate", state = "readonly", command=lambda: navigate_button_click("market"))
market_navigate_button.grid(column=1, row=5, sticky=tk.EW)



#Display the transit time left for the ship to reach a location
market_transit_time = ttk.Label(market_current_location, text = " ", anchor=tk.CENTER)
market_transit_time.grid(row=5, column=2, sticky=tk.EW)




#Buy/Sell/Exchange system

market_purchase_type = tk.StringVar()

market_purchase_type_combobox = ttk.Combobox(
    market_current_location, textvariable=market_purchase_type, postcommand=generate_purchase_type_combobox, state = "readonly", width = 25
)

market_purchase_type_combobox.grid(row=6, column=0, sticky=tk.EW)

market_action_heading = ttk.Label(market_current_location, text = "Please Select Market Action Type", anchor=tk.CENTER)
market_action_heading.grid(row=6, column=1, sticky=tk.EW)


market_process_input = tk.StringVar()

market_process_entry = ttk.Entry(market_current_location, textvariable=market_process_input, state = "readonly")
market_process_entry.grid(column=0, row=7, columnspan=1, sticky=tk.EW)

market_process_button = ttk.Button(market_current_location, text="Proceed", command=proceed_market_action)
market_process_button.grid(column=2, row=7, columnspan=1, sticky=tk.EW)




market_units = tk.StringVar()

market_units_input = ttk.Entry(market_current_location, textvariable=market_units)
market_units_input.grid(column=1, row=7, columnspan=1, sticky=tk.EW)




market_ship_sum.grid(row=1, column=0, columnspan=5, sticky=tk.NSEW)
market_ship_sum.columnconfigure(0, weight=1)
market_ship_sum.rowconfigure(0, weight=1)




market_current_location.columnconfigure(0, weight=1)
market_current_location.grid(row=0, column=0, columnspan=1, sticky=tk.NSEW)




marketplace.columnconfigure(0, weight=1)
marketplace.columnconfigure(1, weight=3)
marketplace.rowconfigure(0, weight=2)
marketplace.rowconfigure(1, weight=3)






root.mainloop()