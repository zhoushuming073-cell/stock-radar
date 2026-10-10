"""QC fill transport; reuse native policy fees, including MOC None references."""
from AlgorithmImports import *
from decimal import Decimal
from sr_execution import fee_components


class ReferenceOpenFee(FeeModel):
    def __init__(self,algorithm):self.algorithm=algorithm

    def get_order_fee(self,parameters):
        a=self.algorithm;key=a.key_for_symbol(parameters.security.symbol)
        q=float(parameters.order.quantity)
        reference=a._sr_context.get(key,{}).get('reference')
        # Fixed-horizon MOC has no Open reference: use native security price.
        if reference is None:reference=float(parameters.security.price)
        price=reference*(1+a._sr_slip*(1 if q>0 else -1))
        fee=fee_components(a._sr_bundle['fees'],abs(q),price,q<0)['total']
        return OrderFee(CashAmount(Decimal(str(fee)),'USD'))


class ReferenceOpenFill(ImmediateFillModel):
    def __init__(self,algorithm):self.algorithm=algorithm

    def market_fill(self,asset,order):
        event=super().market_fill(asset,order)
        if event.status==OrderStatus.FILLED:
            a=self.algorithm;key=a.key_for_symbol(asset.symbol)
            reference=a._sr_context.get(key,{}).get('reference')
            if reference is not None:
                # Observed 09:30 minute Open delivered at09:31, not a backdate.
                event.fill_price=Decimal(str(reference*(1+a._sr_slip*(1 if order.quantity>0 else -1))))
        return event
