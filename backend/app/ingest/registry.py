"""Parsers by dataset_id. C2 adds an entry here when a dataset's parser is merged."""

from app.api.schemas import DatasetSource
from app.ingest.fixture import parse_fixture
from app.ingest.interface import Parser
from app.ingest.nf_v3 import parse_nf_v3
from app.ingest.otrf import parse_otrf
from app.ingest.unsw_nb15 import parse_unsw_nb15

PARSERS: dict[DatasetSource, Parser] = {
    DatasetSource.FIXTURE: parse_fixture,
    DatasetSource.UNSW_NB15: parse_unsw_nb15,
    DatasetSource.NF_UNSW_NB15_V3: parse_nf_v3,
    DatasetSource.NF_CSE_CIC_IDS2018_V3: parse_nf_v3,
    DatasetSource.OTRF: parse_otrf,
}

DATASET_NAMES: dict[DatasetSource, str] = {
    DatasetSource.FIXTURE: "Synthetic fixture (JSON list of Events)",
    DatasetSource.PRECINCT6: "Precinct6 (WitFoo)",
    DatasetSource.UNSW_NB15: "UNSW-NB15",
    DatasetSource.CIC_IDS2017: "CIC-IDS2017",
    DatasetSource.LOGHUB_BGL: "Loghub BGL",
    DatasetSource.LOGHUB_THUNDERBIRD: "Loghub Thunderbird",
    DatasetSource.OTRF: "OTRF Security Datasets",
    DatasetSource.NF_UNSW_NB15_V3: "NF-UNSW-NB15-v3 (UQ NetFlow v3)",
    DatasetSource.NF_CSE_CIC_IDS2018_V3: "NF-CSE-CIC-IDS2018-v3 (UQ NetFlow v3)",
}
