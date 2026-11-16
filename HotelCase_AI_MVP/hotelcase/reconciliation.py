"""Financial rules: deterministic, conservative, in integer cents."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import pandas as pd

REQUIRED = {
 'reservations':{'reservation_id','property_id','channel','payment_responsibility','booking_status','gross_amount','approved_refund','adjustment','ota_commission','currency','response_deadline'},
 'payments':{'payment_id','reservation_id','amount','status','currency','processed_at'},
 'settlements':{'settlement_id','reservation_id','amount','status','currency','settled_at'}
}

class DataValidationError(ValueError): pass

def cents(value) -> int:
    try:
        number=Decimal(str(value).strip())
        if not number.is_finite(): raise ValueError('Nonfinite monetary amount')
        return int((number*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError) as exc:
        raise DataValidationError(f'Invalid currency amount: {value!r}') from exc

def money(c: int) -> str:
    return f'${Decimal(c)/100:,.2f}'

@dataclass(frozen=True)
class Case:
    reservation_id: str
    property_id: str
    channel: str
    payment_responsibility: str
    booking_status: str
    currency: str
    expected_cents: int
    received_cents: int
    discrepancy_cents: int
    category: str
    severity: str
    reason: str
    response_deadline: str
    source_type: str
    evidence_flags: str
    def to_dict(self) -> dict: return asdict(self)

def _clean(data: pd.DataFrame, kind: str) -> pd.DataFrame:
    missing=REQUIRED[kind]-set(data.columns)
    if missing: raise DataValidationError(f'{kind}.csv missing columns: {", ".join(sorted(missing))}')
    df=data.copy().fillna('')
    for column in df.columns:
        df[column]=df[column].astype(str).str.strip()
    if any(not x for x in df['reservation_id']):
        raise DataValidationError(f'{kind}: blank reservation_id')
    return df

def reconcile(reservations: pd.DataFrame, payments: pd.DataFrame, settlements: pd.DataFrame) -> tuple[list[Case], list[str]]:
    r=_clean(reservations,'reservations'); p=_clean(payments,'payments');s=_clean(settlements,'settlements')
    if r['reservation_id'].duplicated().any(): raise DataValidationError('Duplicate reservation_id in reservations file; resolve before reconciliation.')
    warnings=[]
    for name,df,idcol in [('payments',p,'payment_id'),('settlements',s,'settlement_id')]:
        if (df[idcol]=='').any(): raise DataValidationError(f'{name}: blank transaction ID')
        duplicated=df[df[idcol].duplicated(keep=False)]
        if len(duplicated):
            warnings.append(f'{name}: {len(duplicated)} rows have repeated IDs; duplicated IDs are excluded from totals pending manual review.')
        df.drop(df[df[idcol].isin(duplicated[idcol])].index,inplace=True)
    known=set(r['reservation_id'])
    for name,df in [('payments',p),('settlements',s)]:
        unknown=set(df['reservation_id'])-known
        if unknown: warnings.append(f'{name}: transactions reference unknown reservations {sorted(unknown)}; ignored.')
    cases=[]
    for row in r.to_dict('records'):
        rid=row['reservation_id']; currency=row['currency'].upper()
        if currency!='USD': raise DataValidationError(f'{rid}: MVP supports USD only; received {currency}')
        resp=row['payment_responsibility'].upper();status=row['booking_status'].upper()
        if resp not in ('HOTEL','OTA'): raise DataValidationError(f'{rid}: payment_responsibility must be HOTEL or OTA')
        gross=cents(row['gross_amount']);refund=cents(row['approved_refund']);adjust=cents(row['adjustment']);comm=cents(row['ota_commission'])
        if min(gross,refund,adjust,comm)<0 or gross-refund-adjust-(comm if resp=='OTA' else 0)<0:
            raise DataValidationError(f'{rid}: invalid negative or over-adjusted amounts')
        expected=gross-refund-adjust-(comm if resp=='OTA' else 0)
        tx=p if resp=='HOTEL' else s
        relevant=tx[tx['reservation_id']==rid]
        successful='CAPTURED' if resp=='HOTEL' else 'SETTLED'
        relevant_success=relevant[relevant['status'].str.upper()==successful]
        if not relevant_success.empty and (relevant_success['currency'].str.upper()!='USD').any():
            raise DataValidationError(f'{rid}: mixed-currency payment record not supported')
        received=sum(cents(a) for a in relevant_success['amount'])
        discrepancy=expected-received
        dup_original=(payments if resp=='HOTEL' else settlements)
        idcol='payment_id' if resp=='HOTEL' else 'settlement_id'
        dirty=dup_original.copy().fillna('')
        duplicated_ids=set(dirty.loc[dirty[idcol].astype(str).duplicated(keep=False),idcol].astype(str))
        has_dup=bool(set(dirty.loc[dirty['reservation_id'].astype(str)==rid,idcol].astype(str)) & duplicated_ids)
        pending=bool((relevant['status'].str.upper()=='PENDING').any())
        flags=[]
        if has_dup: flags.append('DUPLICATE_TRANSACTION_ID')
        if pending: flags.append('PENDING_TRANSACTION')
        if status in ('CANCELLED','NO_SHOW'):
            cat='POLICY_REVIEW';sev='REVIEW'
            reason='Cancellation/no-show financial eligibility must be verified against applicable policy and ledger.'
        elif has_dup:
            cat='DATA_QUALITY_REVIEW';sev='REVIEW'
            reason='Duplicate transaction ID found. Excluded ambiguous rows; resolve transaction integrity before a revenue claim.'
        elif discrepancy>0 and pending:
            cat='PENDING_VERIFICATION';sev='REVIEW'
            reason='Expected amount exceeds confirmed receipts, but a transaction is pending; verify settlement timing first.'
        elif discrepancy>0:
            cat='SHORTFALL';sev='HIGH' if discrepancy>=10000 else 'MEDIUM'
            reason='Confirmed receipts are below amount expected from the supplied synthetic ledger; verify timing and adjustments.'
        elif discrepancy<0:
            cat='OVER_COLLECTION_REVIEW';sev='REVIEW'
            reason='Confirmed receipts exceed expected amount; investigate refund or ledger errors before taking action.'
        else:
            cat='RECONCILED';sev='NONE';reason='Expected amount equals confirmed receipts in the uploaded records.'
        cases.append(Case(rid,row['property_id'],row['channel'],resp,status,currency,expected,received,discrepancy,cat,sev,reason,row['response_deadline'],'payments' if resp=='HOTEL' else 'settlements',','.join(flags)))
    return cases,warnings
