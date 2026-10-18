from fastapi import HTTPException
from app.database import SessionLocal
from app.models import OrderRequest, OrderDB, AccountDB


def create_order(order_request: OrderRequest) -> OrderDB:
    with SessionLocal() as session:
        account = session.get(AccountDB, 1)

        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        if order_request.side.value == "buy":
            required_cash = order_request.price * order_request.quantity
            available_cash = account.balance - account.reserved_balance

            if available_cash < required_cash:
                raise HTTPException(
                    status_code=400,
                    detail="Insufficient available cash"
                )

            account.reserved_balance += required_cash

        new_order = OrderDB(
            account_id=account.id,
            symbol=order_request.symbol,
            side=order_request.side.value,
            type=order_request.type.value,
            price=order_request.price,
            quantity=order_request.quantity,
            status="open",
            filled_quantity=0,
        )

        session.add(new_order)
        session.commit()
        session.refresh(new_order)
        session.expunge(new_order)
        return new_order
