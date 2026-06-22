from pydantic import BaseModel


class KPIStats(BaseModel):
    today_orders: int
    today_revenue: float
    new_customers_today: int
    pending_orders: int
    open_support_tickets: int
    unresolved_fraud_signals: int
    low_stock_products: int
