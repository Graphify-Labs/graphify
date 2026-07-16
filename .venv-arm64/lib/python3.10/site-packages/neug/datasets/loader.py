#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2020 Alibaba Group Holding Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List
from typing import Optional

from neug.connection import Connection
from neug.database import Database
from neug.datasets.io_utils import DATA_SITE
from neug.datasets.io_utils import download_file

logger = logging.getLogger(__name__)


@dataclass
class DatasetInfo:
    name: str  # The name of the dataset
    description: str  # A brief description of the dataset
    node_types: List[str]  # List of node types in the dataset
    edge_types: List[str]  # List of edge types in the dataset
    create_schema_query: List[str]  # Queries to create the schema for the dataset
    data_import_query: List[str]  # Queries to import data into the dataset
    site: str  # The site where the dataset is hosted
    path: str  # The path to the dataset file or directory


def get_available_datasets() -> List[DatasetInfo]:
    """
    Get a list of available datasets from the dataset manager.

    Returns
    -------
    List[DatasetInfo]
        A list of DatasetInfo objects representing available datasets.
    """
    return [
        DatasetInfo(
            name="modern_graph",
            description="A modern graph dataset with various node and edge types.",
            node_types=["person", "software"],
            edge_types=["knows", "created"],
            create_schema_query=[
                "CREATE NODE TABLE person (id INT32, name STRING, age INT32, PRIMARY KEY(id));",
                "CREATE NODE TABLE software (id INT32, name STRING, lang STRING, PRIMARY KEY(id));",
                "CREATE REL TABLE knows (FROM person TO person, weight DOUBLE);",
                "CREATE REL TABLE created (FROM person TO software, weight DOUBLE, since INT32);",
            ],
            data_import_query=[
                "COPY person from '{}/person.csv'",
                "COPY software from '{}/software.csv'",
                "COPY knows from '{}/person_knows_person.csv'",
                "COPY created from '{}/person_created_software.csv'",
            ],
            site=DATA_SITE,
            path="modern_graph.tar.gz",
        ),
        DatasetInfo(
            name="tinysnb",
            description="A small social network benchmark dataset.",
            node_types=["person", "organisation", "movies"],
            edge_types=["knows", "studyAt", "workAt", "meets", "marries"],
            create_schema_query=[
                "CREATE NODE TABLE person (id INT32, fName STRING, gender INT32, isStudent BOOL, isWorker BOOL, age INT32, "
                "eyeSight DOUBLE, birthdate DATE, registerTime TimeStamp, lastjobDuration Interval, workedHours STRING, "
                "usedNames STRING, courseScoresPerTerm STRING, grades STRING, height DOUBLE, u STRING, PRIMARY KEY(id));",
                "CREATE NODE TABLE organisation (id INT32, name STRING, orgCode INT64, mark DOUBLE, score INT32, "
                "history STRING, licenseValidInterval INTERVAL, rating DOUBLE, state STRING, info STRING, PRIMARY KEY(id));",
                "CREATE NODE TABLE movies (name STRING, length INT32, note STRING, description STRING, content STRING, "
                "audience STRING, grade STRING, PRIMARY KEY(name));",
                "CREATE REL TABLE knows (FROM person TO person, date DATE, meetTime STRING, validInterval INTERVAL, "
                "comments STRING, summary STRING, notes STRING, someMap STRING);",
                "CREATE REL TABLE studyAt (FROM person TO organisation,  year INT32, places STRING, length INT32, "
                "level INT32, code UINT64, temperature INT32, ulength INT32, ulevel INT32, hugedate STRING);",
                "CREATE REL TABLE workAt (FROM person TO organisation, year INT32, grading STRING, rating DOUBLE);",
                "CREATE REL TABLE meets (FROM person TO person, location STRING, times INT32, data STRING);",
                "CREATE REL TABLE marries (FROM person TO person, useAddress STRING, address STRING, note STRING);",
            ],
            data_import_query=[
                "COPY person from '{}/vPerson.csv' (DELIMITER=',', HEADER=true)",
                "COPY organisation from '{}/vOrganisation.csv' (DELIMITER=',', HEADER=true, QUOTE='\"', ESCAPE='\\\\' )",
                "COPY movies from '{}/vMovies.csv' (DELIMITER=',', HEADER=true)",
                "COPY knows from '{}/eKnows.csv' (DELIMITER=',', HEADER=true, QUOTE='\"', ESCAPE='\\\\' )",
                "COPY studyAt from '{}/eStudyAt.csv' (DELIMITER=',', HEADER=true)",
                "COPY workAt from '{}/eWorkAt.csv' (DELIMITER=',', HEADER=true)",
                "COPY meets from '{}/eMeets.csv' (DELIMITER=',', HEADER=true)",
                "COPY marries from '{}/eMarries.csv' (DELIMITER=',', HEADER=true)",
            ],
            site=DATA_SITE,
            path="tinysnb.tar.gz",
        ),
        DatasetInfo(
            name="ogbn_mag_small",
            description="Open Graph Benchmark - MAG (Microsoft Academic Graph) small subset. "
            "A heterogeneous academic graph with papers, authors, institutions, and fields of study.",
            node_types=["paper", "author", "institution", "field_of_study"],
            edge_types=["cites", "writes", "affiliated_with", "has_topic"],
            create_schema_query=[
                "CREATE NODE TABLE paper (id INT64, feat_0 DOUBLE, feat_1 DOUBLE, feat_2 DOUBLE, feat_3 DOUBLE, "
                "feat_4 DOUBLE, feat_5 DOUBLE, feat_6 DOUBLE, feat_7 DOUBLE, feat_8 DOUBLE, feat_9 DOUBLE, "
                "feat_10 DOUBLE, feat_11 DOUBLE, feat_12 DOUBLE, feat_13 DOUBLE, feat_14 DOUBLE, feat_15 DOUBLE, "
                "feat_16 DOUBLE, feat_17 DOUBLE, feat_18 DOUBLE, feat_19 DOUBLE, feat_20 DOUBLE, feat_21 DOUBLE, "
                "feat_22 DOUBLE, feat_23 DOUBLE, feat_24 DOUBLE, feat_25 DOUBLE, feat_26 DOUBLE, feat_27 DOUBLE, "
                "feat_28 DOUBLE, feat_29 DOUBLE, feat_30 DOUBLE, feat_31 DOUBLE, feat_32 DOUBLE, feat_33 DOUBLE, "
                "feat_34 DOUBLE, feat_35 DOUBLE, feat_36 DOUBLE, feat_37 DOUBLE, feat_38 DOUBLE, feat_39 DOUBLE, "
                "feat_40 DOUBLE, feat_41 DOUBLE, feat_42 DOUBLE, feat_43 DOUBLE, feat_44 DOUBLE, feat_45 DOUBLE, "
                "feat_46 DOUBLE, feat_47 DOUBLE, feat_48 DOUBLE, feat_49 DOUBLE, feat_50 DOUBLE, feat_51 DOUBLE, "
                "feat_52 DOUBLE, feat_53 DOUBLE, feat_54 DOUBLE, feat_55 DOUBLE, feat_56 DOUBLE, feat_57 DOUBLE, "
                "feat_58 DOUBLE, feat_59 DOUBLE, feat_60 DOUBLE, feat_61 DOUBLE, feat_62 DOUBLE, feat_63 DOUBLE, "
                "feat_64 DOUBLE, feat_65 DOUBLE, feat_66 DOUBLE, feat_67 DOUBLE, feat_68 DOUBLE, feat_69 DOUBLE, "
                "feat_70 DOUBLE, feat_71 DOUBLE, feat_72 DOUBLE, feat_73 DOUBLE, feat_74 DOUBLE, feat_75 DOUBLE, "
                "feat_76 DOUBLE, feat_77 DOUBLE, feat_78 DOUBLE, feat_79 DOUBLE, feat_80 DOUBLE, feat_81 DOUBLE, "
                "feat_82 DOUBLE, feat_83 DOUBLE, feat_84 DOUBLE, feat_85 DOUBLE, feat_86 DOUBLE, feat_87 DOUBLE, "
                "feat_88 DOUBLE, feat_89 DOUBLE, feat_90 DOUBLE, feat_91 DOUBLE, feat_92 DOUBLE, feat_93 DOUBLE, "
                "feat_94 DOUBLE, feat_95 DOUBLE, feat_96 DOUBLE, feat_97 DOUBLE, feat_98 DOUBLE, feat_99 DOUBLE, "
                "feat_100 DOUBLE, feat_101 DOUBLE, feat_102 DOUBLE, feat_103 DOUBLE, feat_104 DOUBLE, feat_105 DOUBLE, "
                "feat_106 DOUBLE, feat_107 DOUBLE, feat_108 DOUBLE, feat_109 DOUBLE, feat_110 DOUBLE, feat_111 DOUBLE, "
                "feat_112 DOUBLE, feat_113 DOUBLE, feat_114 DOUBLE, feat_115 DOUBLE, feat_116 DOUBLE, feat_117 DOUBLE, "
                "feat_118 DOUBLE, feat_119 DOUBLE, feat_120 DOUBLE, feat_121 DOUBLE, feat_122 DOUBLE, feat_123 DOUBLE, "
                "feat_124 DOUBLE, feat_125 DOUBLE, feat_126 DOUBLE, feat_127 DOUBLE, "
                "year INT32, label INT32, PRIMARY KEY(id));",
                "CREATE NODE TABLE author (id INT64, PRIMARY KEY(id));",
                "CREATE NODE TABLE institution (id INT64, PRIMARY KEY(id));",
                "CREATE NODE TABLE field_of_study (id INT64, PRIMARY KEY(id));",
                "CREATE REL TABLE cites (FROM paper TO paper);",
                "CREATE REL TABLE writes (FROM author TO paper);",
                "CREATE REL TABLE affiliated_with (FROM author TO institution);",
                "CREATE REL TABLE has_topic (FROM paper TO field_of_study);",
            ],
            data_import_query=[
                "COPY paper from '{}/paper.csv' (DELIMITER=',', HEADER=true)",
                "COPY author from '{}/author.csv' (DELIMITER=',', HEADER=true)",
                "COPY institution from '{}/institution.csv' (DELIMITER=',', HEADER=true)",
                "COPY field_of_study from '{}/field_of_study.csv' (DELIMITER=',', HEADER=true)",
                "COPY cites from '{}/paper_cites_paper.csv' (DELIMITER=',', HEADER=true)",
                "COPY writes from '{}/author_writes_paper.csv' (DELIMITER=',', HEADER=true)",
                "COPY affiliated_with from '{}/author_affiliated_with_institution.csv' "
                "(DELIMITER=',', HEADER=true)",
                "COPY has_topic from '{}/paper_has_topic_field_of_study.csv' (DELIMITER=',', HEADER=true)",
            ],
            site=DATA_SITE,
            path="ogbn_mag_small.tar.gz",
        ),
    ]


class DatasetLoader:
    """
    DatasetLoader is a class that provides methods to load datasets into a NeuG database.
    """

    def __init__(self):
        """
        Initialize a DatasetLoader instance.
        """
        self._available_datasets: List[DatasetInfo] = get_available_datasets()

    def _check_schema_conflict(
        self, dataset_info: DatasetInfo, conn: Connection
    ) -> None:
        """
        Check if the schema of the dataset conflicts with the existing schema of the database.

        Parameters
        ----------
        dataset_info : DatasetInfo
            The information about the dataset to check.
        conn : Connection
            The connection to the NeuG database.
        """
        # TODO(zhanglei): currently not checking schema conflict,
        # exceptions will be raised when executing the schema creation queries.
        return

    def _load_dataset_into_connection(
        self, dataset_name: str, conn: Connection
    ) -> None:
        """
        Load a dataset into the specified connection.

        Parameters
        ----------
        dataset_name : str
            The name of the dataset to load.
        conn : Connection
            The connection to the NeuG database where the dataset will be loaded.
        """
        if not conn.is_open:
            raise RuntimeError("Connection is closed. Cannot load dataset.")
        dataset_info = next(
            (ds for ds in self._available_datasets if ds.name == dataset_name), None
        )
        if not dataset_info:
            available = [ds.name for ds in self._available_datasets]
            raise ValueError(
                f"Dataset '{dataset_name}' not found. Available datasets: {available}"
            )

        self._check_schema_conflict(dataset_info, conn)

        full_path = dataset_info.site + "/" + dataset_info.path
        # if is directory
        if Path(full_path).is_dir():
            fpath = full_path
            fpath_extracted = full_path
        else:
            fpath, fpath_extracted = download_file(
                dataset_info.path,
                origin=dataset_info.site + "/" + dataset_info.path,
                extract=True,
            )
        logger.info(f"Downloaded dataset '{dataset_info.name}' to {fpath}")
        # check fpath exists
        if not Path(fpath).exists():
            raise RuntimeError(
                f"Failed to download dataset '{dataset_info.name}' from {dataset_info.site}."
            )
        # Run the schema creation queries
        for query in dataset_info.create_schema_query:
            conn.execute(query)

        # Load the data into the database
        for query in dataset_info.data_import_query:
            query = query.format(fpath_extracted)
            conn.execute(query)
        logger.info(f"Dataset '{dataset_info.name}' loaded successfully.")
        return True

    def load_dataset(self, dataset_name: str, db_path: str = None) -> None:
        """
        Load a dataset into the specified NeuG database.

        Parameters
        ----------
        dataset_name : str
            The name of the dataset to load.
        db_path : str, optional
            The path to the NeuG database. If not provided, a temporary database will be created.
        """

        available_datasets = get_available_datasets()
        if dataset_name not in [ds.name for ds in available_datasets]:
            logger.error(
                f"Dataset '{dataset_name}' not found. Available datasets: {[ds.name for ds in available_datasets]}"
            )
            raise ValueError(f"Dataset '{dataset_name}' not found.")

        if db_path is None:
            db_path = tempfile.mkdtemp(prefix=f"neug_dataset_{dataset_name}_")

        logger.info(f"Loading dataset '{dataset_name}' into database at {db_path}")

        db = Database(db_path, mode="w")
        try:
            with db.connect() as conn:
                self._load_dataset_into_connection(dataset_name, conn)
            logger.info(
                f"Successfully loaded dataset '{dataset_name}' into database at {db_path}"
            )
            return db
        except Exception as e:
            db.close()
            logger.error(f"Failed to load dataset '{dataset_name}': {e}")
            if db_path and Path(db_path).exists():
                shutil.rmtree(db_path)
            raise RuntimeError(f"Failed to load dataset '{dataset_name}': {e}") from e


def load_dataset(
    dataset_name: str, db_path: Optional[str] = None, mode: str = "w"
) -> Database:
    """
    Load a dataset into a NeuG database.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset to load.
    db_path : str, optional
        The path to the NeuG database. If not provided, a temporary database will be created.

    Returns
    -------
    Database
        The loaded NeuG database instance.
    """
    loader = DatasetLoader()
    return loader.load_dataset(dataset_name, db_path)
