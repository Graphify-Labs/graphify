"""
*********
JSON data
*********
Generate and parse JSON serializable data for NetworkX graphs.

These formats are suitable for use with the d3.js examples https://d3js.org/

The three formats that you can generate with NetworkX are:

 - node-link like in the d3.js example https://bl.ocks.org/mbostock/4062045
 - tree like in the d3.js example https://bl.ocks.org/mbostock/4063550
 - adjacency like in the d3.js example https://bost.ocks.org/mike/miserables/
"""

from networkx.readwrite.json_graph.node_link import *
from networkx.readwrite.json_graph.adjacency import *
from networkx.readwrite.json_graph.tree import *
from networkx.readwrite.json_graph.cytoscape import *
