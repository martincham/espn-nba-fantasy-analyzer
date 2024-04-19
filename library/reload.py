from loading import reloadFreeAgents
from loading import reloadLeague


LEAGUEFILE = "league.pickle"
FREEAGENTSFILE = "freeagents.pickle"


league = reloadLeague()
reloadFreeAgents(league)
