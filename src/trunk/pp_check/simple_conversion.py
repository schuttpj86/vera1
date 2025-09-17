import pandapower as pp
from VeraGridEngine.IO.others.pandapower_parser import Panda2VeraGrid, PANDAPOWER_AVAILABLE


pp_net = pp.networks.create_cigre_network_lv()

grid = Panda2VeraGrid(file_or_net=pp_net).get_multicircuit()

print()