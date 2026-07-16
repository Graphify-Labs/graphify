"""
Famous social networks.
"""

import networkx as nx

__all__ = [
    "karate_club_graph",
    "davis_southern_women_graph",
    "florentine_families_graph",
    "les_miserables_graph",
]


@nx._dispatchable(graphs=None, returns_graph=True)
def karate_club_graph():
    """Returns Zachary's Karate Club graph.

    Each node in the returned graph has a node attribute 'club' that
    indicates the name of the club to which the member represented by that node
    belongs, either 'Mr. Hi' or 'Officer'. Each edge has a weight based on the
    number of contexts in which that edge's incident node members interacted.

    The dataset is derived from the 'Club After Split From Data' column of Table 3 in [1]_.
    This was in turn derived from the 'Club After Fission' column of Table 1 in the
    same paper. Note that the nodes are 0-indexed in NetworkX, but 1-indexed in the
    paper (the 'Individual Number in Matrix C' column of Table 3 starts at 1). This
    means, for example, that ``G.nodes[9]["club"]`` returns 'Officer', which
    corresponds to row 10 of Table 3 in the paper.

    Examples
    --------
    To get the name of the club to which a node belongs::

        >>> G = nx.karate_club_graph()
        >>> G.nodes[5]["club"]
        'Mr. Hi'
        >>> G.nodes[9]["club"]
        'Officer'

    References
    ----------
    .. [1] Zachary, Wayne W.
       "An Information Flow Model for Conflict and Fission in Small Groups."
       *Journal of Anthropological Research*, 33, 452--473, (1977).
    """
    # Create the set of all members, and the members of each club.
    all_members = set(range(34))
    club1 = {0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 16, 17, 19, 21}
    # club2 = all_members - club1

    G = nx.Graph()
    G.add_nodes_from(all_members)
    G.name = "Zachary's Karate Club"

    zacharydat = """\
0 4 5 3 3 3 3 2 2 0 2 3 2 3 0 0 0 2 0 2 0 2 0 0 0 0 0 0 0 0 0 2 0 0
4 0 6 3 0 0 0 4 0 0 0 0 0 5 0 0 0 1 0 2 0 2 0 0 0 0 0 0 0 0 2 0 0 0
5 6 0 3 0 0 0 4 5 1 0 0 0 3 0 0 0 0 0 0 0 0 0 0 0 0 0 2 2 0 0 0 3 0
3 3 3 0 0 0 0 3 0 0 0 0 3 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
3 0 0 0 0 0 2 0 0 0 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
3 0 0 0 0 0 5 0 0 0 3 0 0 0 0 0 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
3 0 0 0 2 5 0 0 0 0 0 0 0 0 0 0 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
2 4 4 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
2 0 5 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 3 0 4 3
0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 2
2 0 0 0 3 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
1 0 0 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
3 5 3 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 3
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 3 2
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 3 4
0 0 0 0 0 3 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
2 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 2
2 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 3 1
2 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 2 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 5 0 4 0 2 0 0 5 4
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 2 0 3 0 0 0 2 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 5 2 0 0 0 0 0 0 7 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 4 0 0 0 2
0 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 4 3 0 0 0 0 0 0 0 0 4
0 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 2 0 2
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 3 0 0 4 0 0 0 0 0 3 2
0 2 0 0 0 0 0 0 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 3 3
2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 2 7 0 0 2 0 0 0 4 4
0 0 2 0 0 0 0 0 3 0 0 0 0 0 3 3 0 0 1 0 3 0 2 5 0 0 0 0 0 4 3 4 0 5
0 0 0 0 0 0 0 0 4 2 0 0 0 3 2 4 0 0 2 1 1 0 3 4 0 0 2 4 2 2 3 4 5 0"""

    for row, line in enumerate(zacharydat.split("\n")):
        thisrow = [int(b) for b in line.split()]
        for col, entry in enumerate(thisrow):
            if entry >= 1:
                G.add_edge(row, col, weight=entry)

    # Add the name of each member's club as a node attribute.
    for v in G:
        G.nodes[v]["club"] = "Mr. Hi" if v in club1 else "Officer"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def davis_southern_women_graph():
    """Returns Davis Southern women social network.

    This is a bipartite graph.

    References
    ----------
    .. [1] A. Davis, Gardner, B. B., Gardner, M. R., 1941. Deep South.
        University of Chicago Press, Chicago, IL.
    """
    G = nx.Graph()
    # Top nodes
    women = [
        "Evelyn Jefferson",
        "Laura Mandeville",
        "Theresa Anderson",
        "Brenda Rogers",
        "Charlotte McDowd",
        "Frances Anderson",
        "Eleanor Nye",
        "Pearl Oglethorpe",
        "Ruth DeSand",
        "Verne Sanderson",
        "Myra Liddel",
        "Katherina Rogers",
        "Sylvia Avondale",
        "Nora Fayette",
        "Helen Lloyd",
        "Dorothy Murchison",
        "Olivia Carleton",
        "Flora Price",
    ]
    G.add_nodes_from(women, bipartite=0)
    # Bottom nodes
    events = [
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
        "E7",
        "E8",
        "E9",
        "E10",
        "E11",
        "E12",
        "E13",
        "E14",
    ]
    G.add_nodes_from(events, bipartite=1)

    G.add_edges_from(
        [
            ("Evelyn Jefferson", "E1"),
            ("Evelyn Jefferson", "E2"),
            ("Evelyn Jefferson", "E3"),
            ("Evelyn Jefferson", "E4"),
            ("Evelyn Jefferson", "E5"),
            ("Evelyn Jefferson", "E6"),
            ("Evelyn Jefferson", "E8"),
            ("Evelyn Jefferson", "E9"),
            ("Laura Mandeville", "E1"),
            ("Laura Mandeville", "E2"),
            ("Laura Mandeville", "E3"),
            ("Laura Mandeville", "E5"),
            ("Laura Mandeville", "E6"),
            ("Laura Mandeville", "E7"),
            ("Laura Mandeville", "E8"),
            ("Theresa Anderson", "E2"),
            ("Theresa Anderson", "E3"),
            ("Theresa Anderson", "E4"),
            ("Theresa Anderson", "E5"),
            ("Theresa Anderson", "E6"),
            ("Theresa Anderson", "E7"),
            ("Theresa Anderson", "E8"),
            ("Theresa Anderson", "E9"),
            ("Brenda Rogers", "E1"),
            ("Brenda Rogers", "E3"),
            ("Brenda Rogers", "E4"),
            ("Brenda Rogers", "E5"),
            ("Brenda Rogers", "E6"),
            ("Brenda Rogers", "E7"),
            ("Brenda Rogers", "E8"),
            ("Charlotte McDowd", "E3"),
            ("Charlotte McDowd", "E4"),
            ("Charlotte McDowd", "E5"),
            ("Charlotte McDowd", "E7"),
            ("Frances Anderson", "E3"),
            ("Frances Anderson", "E5"),
            ("Frances Anderson", "E6"),
            ("Frances Anderson", "E8"),
            ("Eleanor Nye", "E5"),
            ("Eleanor Nye", "E6"),
            ("Eleanor Nye", "E7"),
            ("Eleanor Nye", "E8"),
            ("Pearl Oglethorpe", "E6"),
            ("Pearl Oglethorpe", "E8"),
            ("Pearl Oglethorpe", "E9"),
            ("Ruth DeSand", "E5"),
            ("Ruth DeSand", "E7"),
            ("Ruth DeSand", "E8"),
            ("Ruth DeSand", "E9"),
            ("Verne Sanderson", "E7"),
            ("Verne Sanderson", "E8"),
            ("Verne Sanderson", "E9"),
            ("Verne Sanderson", "E12"),
            ("Myra Liddel", "E8"),
            ("Myra Liddel", "E9"),
            ("Myra Liddel", "E10"),
            ("Myra Liddel", "E12"),
            ("Katherina Rogers", "E8"),
            ("Katherina Rogers", "E9"),
            ("Katherina Rogers", "E10"),
            ("Katherina Rogers", "E12"),
            ("Katherina Rogers", "E13"),
            ("Katherina Rogers", "E14"),
            ("Sylvia Avondale", "E7"),
            ("Sylvia Avondale", "E8"),
            ("Sylvia Avondale", "E9"),
            ("Sylvia Avondale", "E10"),
            ("Sylvia Avondale", "E12"),
            ("Sylvia Avondale", "E13"),
            ("Sylvia Avondale", "E14"),
            ("Nora Fayette", "E6"),
            ("Nora Fayette", "E7"),
            ("Nora Fayette", "E9"),
            ("Nora Fayette", "E10"),
            ("Nora Fayette", "E11"),
            ("Nora Fayette", "E12"),
            ("Nora Fayette", "E13"),
            ("Nora Fayette", "E14"),
            ("Helen Lloyd", "E7"),
            ("Helen Lloyd", "E8"),
            ("Helen Lloyd", "E10"),
            ("Helen Lloyd", "E11"),
            ("Helen Lloyd", "E12"),
            ("Dorothy Murchison", "E8"),
            ("Dorothy Murchison", "E9"),
            ("Olivia Carleton", "E9"),
            ("Olivia Carleton", "E11"),
            ("Flora Price", "E9"),
            ("Flora Price", "E11"),
        ]
    )
    G.graph["top"] = women
    G.graph["bottom"] = events
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def florentine_families_graph():
    """Returns Florentine families graph.

    References
    ----------
    .. [1] Ronald L. Breiger and Philippa E. Pattison
       Cumulated social roles: The duality of persons and their algebras,1
       Social Networks, Volume 8, Issue 3, September 1986, Pages 215-256
    """
    G = nx.Graph()
    G.add_edge("Acciaiuoli", "Medici")
    G.add_edge("Castellani", "Peruzzi")
    G.add_edge("Castellani", "Strozzi")
    G.add_edge("Castellani", "Barbadori")
    G.add_edge("Medici", "Barbadori")
    G.add_edge("Medici", "Ridolfi")
    G.add_edge("Medici", "Tornabuoni")
    G.add_edge("Medici", "Albizzi")
    G.add_edge("Medici", "Salviati")
    G.add_edge("Salviati", "Pazzi")
    G.add_edge("Peruzzi", "Strozzi")
    G.add_edge("Peruzzi", "Bischeri")
    G.add_edge("Strozzi", "Ridolfi")
    G.add_edge("Strozzi", "Bischeri")
    G.add_edge("Ridolfi", "Tornabuoni")
    G.add_edge("Tornabuoni", "Guadagni")
    G.add_edge("Albizzi", "Ginori")
    G.add_edge("Albizzi", "Guadagni")
    G.add_edge("Bischeri", "Guadagni")
    G.add_edge("Guadagni", "Lamberteschi")
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def les_miserables_graph():
    """Returns coappearance network of characters in the novel Les Miserables.

    References
    ----------
    .. [1] D. E. Knuth, 1993.
       The Stanford GraphBase: a platform for combinatorial computing,
       pp. 74-87. New York: AcM Press.
    """
    G = nx.Graph()
    G.add_edge("Napoleon", "Myriel", weight=1)
    G.add_edge("MlleBaptistine", "Myriel", weight=8)
    G.add_edge("MmeMagloire", "Myriel", weight=10)
    G.add_edge("MmeMagloire", "MlleBaptistine", weight=6)
    G.add_edge("CountessDeLo", "Myriel", weight=1)
    G.add_edge("Geborand", "Myriel", weight=1)
    G.add_edge("Champtercier", "Myriel", weight=1)
    G.add_edge("Cravatte", "Myriel", weight=1)
    G.add_edge("Count", "Myriel", weight=2)
    G.add_edge("OldMan", "Myriel", weight=1)
    G.add_edge("Valjean", "Labarre", weight=1)
    G.add_edge("Valjean", "MmeMagloire", weight=3)
    G.add_edge("Valjean", "MlleBaptistine", weight=3)
    G.add_edge("Valjean", "Myriel", weight=5)
    G.add_edge("Marguerite", "Valjean", weight=1)
    G.add_edge("MmeDeR", "Valjean", weight=1)
    G.add_edge("Isabeau", "Valjean", weight=1)
    G.add_edge("Gervais", "Valjean", weight=1)
    G.add_edge("Listolier", "Tholomyes", weight=4)
    G.add_edge("Fameuil", "Tholomyes", weight=4)
    G.add_edge("Fameuil", "Listolier", weight=4)
    G.add_edge("Blacheville", "Tholomyes", weight=4)
    G.add_edge("Blacheville", "Listolier", weight=4)
    G.add_edge("Blacheville", "Fameuil", weight=4)
    G.add_edge("Favourite", "Tholomyes", weight=3)
    G.add_edge("Favourite", "Listolier", weight=3)
    G.add_edge("Favourite", "Fameuil", weight=3)
    G.add_edge("Favourite", "Blacheville", weight=4)
    G.add_edge("Dahlia", "Tholomyes", weight=3)
    G.add_edge("Dahlia", "Listolier", weight=3)
    G.add_edge("Dahlia", "Fameuil", weight=3)
    G.add_edge("Dahlia", "Blacheville", weight=3)
    G.add_edge("Dahlia", "Favourite", weight=5)
    G.add_edge("Zephine", "Tholomyes", weight=3)
    G.add_edge("Zephine", "Listolier", weight=3)
    G.add_edge("Zephine", "Fameuil", weight=3)
    G.add_edge("Zephine", "Blacheville", weight=3)
    G.add_edge("Zephine", "Favourite", weight=4)
    G.add_edge("Zephine", "Dahlia", weight=4)
    G.add_edge("Fantine", "Tholomyes", weight=3)
    G.add_edge("Fantine", "Listolier", weight=3)
    G.add_edge("Fantine", "Fameuil", weight=3)
    G.add_edge("Fantine", "Blacheville", weight=3)
    G.add_edge("Fantine", "Favourite", weight=4)
    G.add_edge("Fantine", "Dahlia", weight=4)
    G.add_edge("Fantine", "Zephine", weight=4)
    G.add_edge("Fantine", "Marguerite", weight=2)
    G.add_edge("Fantine", "Valjean", weight=9)
    G.add_edge("MmeThenardier", "Fantine", weight=2)
    G.add_edge("MmeThenardier", "Valjean", weight=7)
    G.add_edge("Thenardier", "MmeThenardier", weight=13)
    G.add_edge("Thenardier", "Fantine", weight=1)
    G.add_edge("Thenardier", "Valjean", weight=12)
    G.add_edge("Cosette", "MmeThenardier", weight=4)
    G.add_edge("Cosette", "Valjean", weight=31)
    G.add_edge("Cosette", "Tholomyes", weight=1)
    G.add_edge("Cosette", "Thenardier", weight=1)
    G.add_edge("Javert", "Valjean", weight=17)
    G.add_edge("Javert", "Fantine", weight=5)
    G.add_edge("Javert", "Thenardier", weight=5)
    G.add_edge("Javert", "MmeThenardier", weight=1)
    G.add_edge("Javert", "Cosette", weight=1)
    G.add_edge("Fauchelevent", "Valjean", weight=8)
    G.add_edge("Fauchelevent", "Javert", weight=1)
    G.add_edge("Bamatabois", "Fantine", weight=1)
    G.add_edge("Bamatabois", "Javert", weight=1)
    G.add_edge("Bamatabois", "Valjean", weight=2)
    G.add_edge("Perpetue", "Fantine", weight=1)
    G.add_edge("Simplice", "Perpetue", weight=2)
    G.add_edge("Simplice", "Valjean", weight=3)
    G.add_edge("Simplice", "Fantine", weight=2)
    G.add_edge("Simplice", "Javert", weight=1)
    G.add_edge("Scaufflaire", "Valjean", weight=1)
    G.add_edge("Woman1", "Valjean", weight=2)
    G.add_edge("Woman1", "Javert", weight=1)
    G.add_edge("Judge", "Valjean", weight=3)
    G.add_edge("Judge", "Bamatabois", weight=2)
    G.add_edge("Champmathieu", "Valjean", weight=3)
    G.add_edge("Champmathieu", "Judge", weight=3)
    G.add_edge("Champmathieu", "Bamatabois", weight=2)
    G.add_edge("Brevet", "Judge", weight=2)
    G.add_edge("Brevet", "Champmathieu", weight=2)
    G.add_edge("Brevet", "Valjean", weight=2)
    G.add_edge("Brevet", "Bamatabois", weight=1)
    G.add_edge("Chenildieu", "Judge", weight=2)
    G.add_edge("Chenildieu", "Champmathieu", weight=2)
    G.add_edge("Chenildieu", "Brevet", weight=2)
    G.add_edge("Chenildieu", "Valjean", weight=2)
    G.add_edge("Chenildieu", "Bamatabois", weight=1)
    G.add_edge("Cochepaille", "Judge", weight=2)
    G.add_edge("Cochepaille", "Champmathieu", weight=2)
    G.add_edge("Cochepaille", "Brevet", weight=2)
    G.add_edge("Cochepaille", "Chenildieu", weight=2)
    G.add_edge("Cochepaille", "Valjean", weight=2)
    G.add_edge("Cochepaille", "Bamatabois", weight=1)
    G.add_edge("Pontmercy", "Thenardier", weight=1)
    G.add_edge("Boulatruelle", "Thenardier", weight=1)
    G.add_edge("Eponine", "MmeThenardier", weight=2)
    G.add_edge("Eponine", "Thenardier", weight=3)
    G.add_edge("Anzelma", "Eponine", weight=2)
    G.add_edge("Anzelma", "Thenardier", weight=2)
    G.add_edge("Anzelma", "MmeThenardier", weight=1)
    G.add_edge("Woman2", "Valjean", weight=3)
    G.add_edge("Woman2", "Cosette", weight=1)
    G.add_edge("Woman2", "Javert", weight=1)
    G.add_edge("MotherInnocent", "Fauchelevent", weight=3)
    G.add_edge("MotherInnocent", "Valjean", weight=1)
    G.add_edge("Gribier", "Fauchelevent", weight=2)
    G.add_edge("MmeBurgon", "Jondrette", weight=1)
    G.add_edge("Gavroche", "MmeBurgon", weight=2)
    G.add_edge("Gavroche", "Thenardier", weight=1)
    G.add_edge("Gavroche", "Javert", weight=1)
    G.add_edge("Gavroche", "Valjean", weight=1)
    G.add_edge("Gillenormand", "Cosette", weight=3)
    G.add_edge("Gillenormand", "Valjean", weight=2)
    G.add_edge("Magnon", "Gillenormand", weight=1)
    G.add_edge("Magnon", "MmeThenardier", weight=1)
    G.add_edge("MlleGillenormand", "Gillenormand", weight=9)
    G.add_edge("MlleGillenormand", "Cosette", weight=2)
    G.add_edge("MlleGillenormand", "Valjean", weight=2)
    G.add_edge("MmePontmercy", "MlleGillenormand", weight=1)
    G.add_edge("MmePontmercy", "Pontmercy", weight=1)
    G.add_edge("MlleVaubois", "MlleGillenormand", weight=1)
    G.add_edge("LtGillenormand", "MlleGillenormand", weight=2)
    G.add_edge("LtGillenormand", "Gillenormand", weight=1)
    G.add_edge("LtGillenormand", "Cosette", weight=1)
    G.add_edge("Marius", "MlleGillenormand", weight=6)
    G.add_edge("Marius", "Gillenormand", weight=12)
    G.add_edge("Marius", "Pontmercy", weight=1)
    G.add_edge("Marius", "LtGillenormand", weight=1)
    G.add_edge("Marius", "Cosette", weight=21)
    G.add_edge("Marius", "Valjean", weight=19)
    G.add_edge("Marius", "Tholomyes", weight=1)
    G.add_edge("Marius", "Thenardier", weight=2)
    G.add_edge("Marius", "Eponine", weight=5)
    G.add_edge("Marius", "Gavroche", weight=4)
    G.add_edge("BaronessT", "Gillenormand", weight=1)
    G.add_edge("BaronessT", "Marius", weight=1)
    G.add_edge("Mabeuf", "Marius", weight=1)
    G.add_edge("Mabeuf", "Eponine", weight=1)
    G.add_edge("Mabeuf", "Gavroche", weight=1)
    G.add_edge("Enjolras", "Marius", weight=7)
    G.add_edge("Enjolras", "Gavroche", weight=7)
    G.add_edge("Enjolras", "Javert", weight=6)
    G.add_edge("Enjolras", "Mabeuf", weight=1)
    G.add_edge("Enjolras", "Valjean", weight=4)
    G.add_edge("Combeferre", "Enjolras", weight=15)
    G.add_edge("Combeferre", "Marius", weight=5)
    G.add_edge("Combeferre", "Gavroche", weight=6)
    G.add_edge("Combeferre", "Mabeuf", weight=2)
    G.add_edge("Prouvaire", "Gavroche", weight=1)
    G.add_edge("Prouvaire", "Enjolras", weight=4)
    G.add_edge("Prouvaire", "Combeferre", weight=2)
    G.add_edge("Feuilly", "Gavroche", weight=2)
    G.add_edge("Feuilly", "Enjolras", weight=6)
    G.add_edge("Feuilly", "Prouvaire", weight=2)
    G.add_edge("Feuilly", "Combeferre", weight=5)
    G.add_edge("Feuilly", "Mabeuf", weight=1)
    G.add_edge("Feuilly", "Marius", weight=1)
    G.add_edge("Courfeyrac", "Marius", weight=9)
    G.add_edge("Courfeyrac", "Enjolras", weight=17)
    G.add_edge("Courfeyrac", "Combeferre", weight=13)
    G.add_edge("Courfeyrac", "Gavroche", weight=7)
    G.add_edge("Courfeyrac", "Mabeuf", weight=2)
    G.add_edge("Courfeyrac", "Eponine", weight=1)
    G.add_edge("Courfeyrac", "Feuilly", weight=6)
    G.add_edge("Courfeyrac", "Prouvaire", weight=3)
    G.add_edge("Bahorel", "Combeferre", weight=5)
    G.add_edge("Bahorel", "Gavroche", weight=5)
    G.add_edge("Bahorel", "Courfeyrac", weight=6)
    G.add_edge("Bahorel", "Mabeuf", weight=2)
    G.add_edge("Bahorel", "Enjolras", weight=4)
    G.add_edge("Bahorel", "Feuilly", weight=3)
    G.add_edge("Bahorel", "Prouvaire", weight=2)
    G.add_edge("Bahorel", "Marius", weight=1)
    G.add_edge("Bossuet", "Marius", weight=5)
    G.add_edge("Bossuet", "Courfeyrac", weight=12)
    G.add_edge("Bossuet", "Gavroche", weight=5)
    G.add_edge("Bossuet", "Bahorel", weight=4)
    G.add_edge("Bossuet", "Enjolras", weight=10)
    G.add_edge("Bossuet", "Feuilly", weight=6)
    G.add_edge("Bossuet", "Prouvaire", weight=2)
    G.add_edge("Bossuet", "Combeferre", weight=9)
    G.add_edge("Bossuet", "Mabeuf", weight=1)
    G.add_edge("Bossuet", "Valjean", weight=1)
    G.add_edge("Joly", "Bahorel", weight=5)
    G.add_edge("Joly", "Bossuet", weight=7)
    G.add_edge("Joly", "Gavroche", weight=3)
    G.add_edge("Joly", "Courfeyrac", weight=5)
    G.add_edge("Joly", "Enjolras", weight=5)
    G.add_edge("Joly", "Feuilly", weight=5)
    G.add_edge("Joly", "Prouvaire", weight=2)
    G.add_edge("Joly", "Combeferre", weight=5)
    G.add_edge("Joly", "Mabeuf", weight=1)
    G.add_edge("Joly", "Marius", weight=2)
    G.add_edge("Grantaire", "Bossuet", weight=3)
    G.add_edge("Grantaire", "Enjolras", weight=3)
    G.add_edge("Grantaire", "Combeferre", weight=1)
    G.add_edge("Grantaire", "Courfeyrac", weight=2)
    G.add_edge("Grantaire", "Joly", weight=2)
    G.add_edge("Grantaire", "Gavroche", weight=1)
    G.add_edge("Grantaire", "Bahorel", weight=1)
    G.add_edge("Grantaire", "Feuilly", weight=1)
    G.add_edge("Grantaire", "Prouvaire", weight=1)
    G.add_edge("MotherPlutarch", "Mabeuf", weight=3)
    G.add_edge("Gueulemer", "Thenardier", weight=5)
    G.add_edge("Gueulemer", "Valjean", weight=1)
    G.add_edge("Gueulemer", "MmeThenardier", weight=1)
    G.add_edge("Gueulemer", "Javert", weight=1)
    G.add_edge("Gueulemer", "Gavroche", weight=1)
    G.add_edge("Gueulemer", "Eponine", weight=1)
    G.add_edge("Babet", "Thenardier", weight=6)
    G.add_edge("Babet", "Gueulemer", weight=6)
    G.add_edge("Babet", "Valjean", weight=1)
    G.add_edge("Babet", "MmeThenardier", weight=1)
    G.add_edge("Babet", "Javert", weight=2)
    G.add_edge("Babet", "Gavroche", weight=1)
    G.add_edge("Babet", "Eponine", weight=1)
    G.add_edge("Claquesous", "Thenardier", weight=4)
    G.add_edge("Claquesous", "Babet", weight=4)
    G.add_edge("Claquesous", "Gueulemer", weight=4)
    G.add_edge("Claquesous", "Valjean", weight=1)
    G.add_edge("Claquesous", "MmeThenardier", weight=1)
    G.add_edge("Claquesous", "Javert", weight=1)
    G.add_edge("Claquesous", "Eponine", weight=1)
    G.add_edge("Claquesous", "Enjolras", weight=1)
    G.add_edge("Montparnasse", "Javert", weight=1)
    G.add_edge("Montparnasse", "Babet", weight=2)
    G.add_edge("Montparnasse", "Gueulemer", weight=2)
    G.add_edge("Montparnasse", "Claquesous", weight=2)
    G.add_edge("Montparnasse", "Valjean", weight=1)
    G.add_edge("Montparnasse", "Gavroche", weight=1)
    G.add_edge("Montparnasse", "Eponine", weight=1)
    G.add_edge("Montparnasse", "Thenardier", weight=1)
    G.add_edge("Toussaint", "Cosette", weight=2)
    G.add_edge("Toussaint", "Javert", weight=1)
    G.add_edge("Toussaint", "Valjean", weight=1)
    G.add_edge("Child1", "Gavroche", weight=2)
    G.add_edge("Child2", "Gavroche", weight=2)
    G.add_edge("Child2", "Child1", weight=3)
    G.add_edge("Brujon", "Babet", weight=3)
    G.add_edge("Brujon", "Gueulemer", weight=3)
    G.add_edge("Brujon", "Thenardier", weight=3)
    G.add_edge("Brujon", "Gavroche", weight=1)
    G.add_edge("Brujon", "Eponine", weight=1)
    G.add_edge("Brujon", "Claquesous", weight=1)
    G.add_edge("Brujon", "Montparnasse", weight=1)
    G.add_edge("MmeHucheloup", "Bossuet", weight=1)
    G.add_edge("MmeHucheloup", "Joly", weight=1)
    G.add_edge("MmeHucheloup", "Grantaire", weight=1)
    G.add_edge("MmeHucheloup", "Bahorel", weight=1)
    G.add_edge("MmeHucheloup", "Courfeyrac", weight=1)
    G.add_edge("MmeHucheloup", "Gavroche", weight=1)
    G.add_edge("MmeHucheloup", "Enjolras", weight=1)
    return G
