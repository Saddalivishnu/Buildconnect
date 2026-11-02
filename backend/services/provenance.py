from enum import Enum
from typing import Dict, Any

class DataProvenance(str, Enum):
    REAL_WPI = "REAL_WPI"
    USER_ENTERED = "USER_ENTERED"
    REAL_TRANSACTION = "REAL_TRANSACTION"
    SYNTHETIC_RESEARCH = "SYNTHETIC_RESEARCH"
    DEMO = "DEMO"
    SIMULATED_SCENARIO = "SIMULATED_SCENARIO"

PROVENANCE_DESCRIPTIONS: Dict[str, str] = {
    DataProvenance.REAL_WPI.value: "Official historical Wholesale Price Index (WPI) time-series data (2012-2026).",
    DataProvenance.USER_ENTERED.value: "Direct contractor, supplier, or administrator user input.",
    DataProvenance.REAL_TRANSACTION.value: "Actual completed purchase order and verified delivery outcome.",
    DataProvenance.SYNTHETIC_RESEARCH.value: "Synthetic order simulation dataset used solely for research baseline benchmarking.",
    DataProvenance.DEMO.value: "Demonstration seed entity for platform illustration and initial onboarding.",
    DataProvenance.SIMULATED_SCENARIO.value: "What-if simulated procurement assumption; not an executed market order.",
}

def tag_provenance(record: Dict[str, Any], provenance: DataProvenance) -> Dict[str, Any]:
    record["provenance"] = provenance.value
    record["provenance_description"] = PROVENANCE_DESCRIPTIONS.get(provenance.value, "")
    return record
