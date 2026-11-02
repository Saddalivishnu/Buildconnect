
# BuildConnect AI — Final ML/Data Package

Created:
2026-10-08T13:04:06.808794

## ML Pipeline

Real WPI Data
    ↓
Price Forecasting
    ↓
Conformal Prediction
    ↓
Buy / Wait Decision
    ↓
Supplier Risk
    ↓
Supplier Ranking
    ↓
Procurement Optimization
    ↓
Final Recommendation

## Main Research Components

### Price Forecasting
- Real WPI data
- Trend-adjusted forecast
- ARIMA
- XGBoost
- LSTM
- TFT
- Conformal prediction

### Supplier Risk
- Synthetic supplier/order dataset
- Temporal evaluation
- Logistic Regression
- Random Forest
- XGBoost
- SHAP

### Procurement
- Supplier ranking
- Cost optimization
- Risk optimization
- Delivery optimization
- NSGA-II
- Pareto analysis

## IMPORTANT

The supplier/order dataset is synthetic.

It must be described in the research paper as:

"Synthetic Supplier-Risk Simulation / Proof-of-Concept"

It must NOT be represented as real supplier transaction data.

The WPI dataset is real historical index data.

## Next Stage

After this package is downloaded and preserved:

1. Flask backend
2. PostgreSQL/PostGIS
3. ML API endpoints
4. React frontend
5. Supplier marketplace
6. Procurement dashboard
7. Maps
8. AI recommendation interface
