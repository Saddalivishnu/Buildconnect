import csv
import io
from datetime import datetime, date
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd

IMPORT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "material_listings": {
        "required_columns": ["material_name", "quoted_unit_price", "available_quantity", "estimated_delivery_days"],
        "optional_columns": ["minimum_order_quantity", "unit", "availability_status", "quote_valid_until"],
    },
    "supplier_quotations": {
        "required_columns": ["material", "quote_price", "available_quantity", "delivery_days"],
        "optional_columns": ["minimum_order_quantity", "unit", "distance_km", "valid_until"],
    },
    "delivery_outcomes": {
        "required_columns": ["order_id", "actual_delivery_date", "final_paid_price", "cancelled"],
        "optional_columns": ["actual_quantity_received", "delay_days", "cancellation_status", "delivery_status"],
    },
    "wpi_observations": {
        "required_columns": ["material_name", "observation_date", "index_value"],
        "optional_columns": ["data_source"],
    },
}

def validate_csv_import(
    import_type: str,
    file_content: str,
    valid_materials: Optional[set] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parses and validates CSV content against expected schemas.
    Returns: (valid_rows, error_rows, summary)
    """
    schema = IMPORT_SCHEMAS.get(import_type)
    if not schema:
        raise ValueError(f"Unsupported import type: '{import_type}'. Supported: {list(IMPORT_SCHEMAS.keys())}")

    f = io.StringIO(file_content.strip())
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        return [], [], {"total_rows": 0, "valid_count": 0, "error_count": 0, "message": "CSV file is empty or missing headers."}

    missing_cols = [c for c in schema["required_columns"] if c not in reader.fieldnames]
    if missing_cols:
        return [], [], {
            "total_rows": 0,
            "valid_count": 0,
            "error_count": 0,
            "message": f"CSV is missing required headers: {', '.join(missing_cols)}",
        }

    valid_rows = []
    error_rows = []

    for row_idx, raw_row in enumerate(reader, start=1):
        errors = []
        cleaned: Dict[str, Any] = {}

        # Validate by type
        if import_type == "material_listings" or import_type == "supplier_quotations":
            mat_key = "material_name" if "material_name" in raw_row else "material"
            mat_name = str(raw_row.get(mat_key, "")).strip()
            if not mat_name:
                errors.append("Material name is required.")
            elif valid_materials and mat_name not in valid_materials:
                errors.append(f"Material '{mat_name}' does not match official material catalogue.")
            cleaned["material_name"] = mat_name
            cleaned["material"] = mat_name

            price_key = "quoted_unit_price" if "quoted_unit_price" in raw_row else "quote_price"
            try:
                price = float(raw_row.get(price_key, 0))
                if price <= 0:
                    errors.append("Price must be greater than zero.")
                cleaned["quote_price"] = price
                cleaned["quoted_unit_price"] = price
            except ValueError:
                errors.append(f"Invalid numeric value for {price_key}.")

            try:
                avail = float(raw_row.get("available_quantity", 0))
                if avail < 0:
                    errors.append("Available quantity cannot be negative.")
                cleaned["available_quantity"] = avail
            except ValueError:
                errors.append("Invalid numeric value for available_quantity.")

            days_key = "estimated_delivery_days" if "estimated_delivery_days" in raw_row else "delivery_days"
            try:
                days = int(raw_row.get(days_key, 0))
                if days < 1 or days > 365:
                    errors.append("Delivery days must be between 1 and 365.")
                cleaned["delivery_days"] = days
                cleaned["estimated_delivery_days"] = days
            except ValueError:
                errors.append(f"Invalid integer for {days_key}.")

            cleaned["minimum_order_quantity"] = float(raw_row.get("minimum_order_quantity", 1.0) or 1.0)
            cleaned["unit"] = str(raw_row.get("unit", "Metric Ton") or "Metric Ton")
            cleaned["distance_km"] = float(raw_row.get("distance_km", 0.0) or 0.0)

        elif import_type == "delivery_outcomes":
            try:
                cleaned["order_id"] = int(raw_row.get("order_id", 0))
            except ValueError:
                errors.append("order_id must be a valid integer.")

            actual_date_str = str(raw_row.get("actual_delivery_date", "")).strip()
            cancelled = str(raw_row.get("cancelled", "0")).strip() in {"1", "true", "True"}
            cleaned["cancelled"] = int(cancelled)

            if not cancelled:
                try:
                    parsed_date = date.fromisoformat(actual_date_str)
                    if parsed_date > date.today():
                        errors.append("actual_delivery_date cannot be in the future.")
                    cleaned["actual_delivery_date"] = actual_date_str
                except ValueError:
                    errors.append("actual_delivery_date must be formatted YYYY-MM-DD.")
            else:
                cleaned["actual_delivery_date"] = None

            try:
                cleaned["final_paid_price"] = float(raw_row.get("final_paid_price", 0.0))
            except ValueError:
                errors.append("final_paid_price must be a valid number.")

            cleaned["delay_days"] = int(raw_row.get("delay_days", 0) or 0)
            cleaned["cancellation_status"] = str(raw_row.get("cancellation_status", "none"))
            cleaned["delivery_status"] = str(raw_row.get("delivery_status", "delivered" if not cancelled else "cancelled"))

        elif import_type == "wpi_observations":
            mat_name = str(raw_row.get("material_name", "")).strip()
            if not mat_name:
                errors.append("material_name is required.")
            elif valid_materials and mat_name not in valid_materials:
                errors.append(f"Material '{mat_name}' not found in WPI catalogue.")
            cleaned["material_name"] = mat_name

            obs_date = str(raw_row.get("observation_date", "")).strip()
            try:
                date.fromisoformat(obs_date)
                cleaned["observation_date"] = obs_date
            except ValueError:
                errors.append("observation_date must be formatted YYYY-MM-DD.")

            try:
                idx_val = float(raw_row.get("index_value", 0))
                if idx_val <= 0:
                    errors.append("index_value must be greater than zero.")
                cleaned["index_value"] = idx_val
            except ValueError:
                errors.append("index_value must be a valid number.")

            cleaned["data_source"] = str(raw_row.get("data_source", "REAL_WPI") or "REAL_WPI")

        if errors:
            error_rows.append({"row_number": row_idx, "raw_data": raw_row, "errors": errors})
        else:
            valid_rows.append(cleaned)

    summary = {
        "total_rows": len(valid_rows) + len(error_rows),
        "valid_count": len(valid_rows),
        "error_count": len(error_rows),
        "preview_sample": valid_rows[:5],
    }

    return valid_rows, error_rows, summary
