"""Mock SAP interface. Replace method bodies with real RFC / REST calls."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class SAPOrder:
    order_id: str
    patient_id: str
    product: str
    priority: int
    created_date: datetime
    status: str = "Released"


class SAPInterface:
    def __init__(self):
        self._orders: List[SAPOrder] = []

    def add_order(
        self,
        order_id: str,
        patient_id: str,
        product: str,
        priority: int,
        created_date: Optional[datetime] = None,
    ) -> SAPOrder:
        order = SAPOrder(
            order_id=order_id,
            patient_id=patient_id,
            product=product,
            priority=priority,
            created_date=created_date or datetime.now(),
        )
        self._orders.append(order)
        return order

    def get_released_orders(self, product: Optional[str] = None) -> List[SAPOrder]:
        orders = [o for o in self._orders if o.status == "Released"]
        if product:
            orders = [o for o in orders if o.product == product]
        return sorted(orders, key=lambda o: o.priority)

    def get_order(self, order_id: str) -> Optional[SAPOrder]:
        return next((o for o in self._orders if o.order_id == order_id), None)

    def set_status(self, order_id: str, status: str):
        order = self.get_order(order_id)
        if order:
            order.status = status

    def all_orders(self) -> List[SAPOrder]:
        return list(self._orders)
