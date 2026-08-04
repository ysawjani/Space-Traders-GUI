# SpaceTraders GUI

A GUI client for SpaceTraders, a game that's normally only playable through 
raw API requests. Built in Python with Tkinter for my NEA prep project.

## What it does

Started from a base template (login, summary, and leaderboard tabs) given 
by my teacher. I added two new tabs:

**Ships tab** — scan nearby waypoints, navigate between them (with a live 
countdown), dock/orbit, refuel, and extract resources

**Marketplace tab** — view nearby marketplaces and buy/sell/exchange goods, 
with credits updating after each trade


Needs `requests` installed (`pip install requests`). 

The register feature was having server side issues at time of build, so its functionality is unconfirmed.
