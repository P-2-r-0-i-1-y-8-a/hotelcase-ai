"""Deterministic, wholly fictional demonstration data."""
from pathlib import Path
import csv

RESERVATIONS = [
# reservation, property, OTA, responsibility, booking, gross, refund, adjustment, commission, currency, deadline
('HC-1001','CLT-01','Booking.com','HOTEL','CHECKED_OUT','320.00','0','0','0','USD',''),
('HC-1002','CLT-01','Expedia','OTA','CHECKED_OUT','500.00','0','0','75.00','USD',''),
('HC-1003','CLT-01','Direct','HOTEL','CHECKED_OUT','250.00','0','0','0','USD',''),
('HC-1004','CLT-01','Booking.com','HOTEL','CHECKED_OUT','180.00','0','0','0','USD','2026-12-01'),
('HC-1005','RDU-02','Expedia','OTA','CHECKED_OUT','400.00','50.00','0','60.00','USD',''),
('HC-1006','RDU-02','Direct','HOTEL','CHECKED_OUT','150.00','0','0','0','USD',''),
('HC-1007','RDU-02','Booking.com','HOTEL','CANCELLED','190.00','0','0','0','USD',''),
('HC-1008','CLT-01','Booking.com','OTA','CHECKED_OUT','220.00','0','0','33.00','USD',''),
('HC-1009','CLT-01','Direct','HOTEL','CHECKED_OUT','100.00','0','0','0','USD',''),
('HC-1010','RDU-02','Expedia','OTA','CHECKED_OUT','300.00','0','0','45.00','USD',''),
('HC-1011','RDU-02','Direct','HOTEL','NO_SHOW','120.00','0','0','0','USD',''),
('HC-1012','CLT-01','Direct','HOTEL','CHECKED_OUT','275.00','0','25.00','0','USD',''),
('HC-1013','CLT-01','Booking.com','HOTEL','CHECKED_OUT','200.00','0','0','0','USD',''),
('HC-1014','RDU-02','Expedia','OTA','CHECKED_OUT','160.00','0','0','24.00','USD',''),
]
PAYMENTS = [
# payment id, reservation id, amount, state, currency, processed_at
('PAY-001','HC-1001','220.00','CAPTURED','USD','2026-11-01'),
('PAY-002','HC-1003','250.00','CAPTURED','USD','2026-11-01'),
('PAY-003','HC-1004','180.00','PENDING','USD','2026-11-01'),
('PAY-004','HC-1006','170.00','CAPTURED','USD','2026-11-02'),
('PAY-005','HC-1007','0.00','VOIDED','USD','2026-11-02'),
('PAY-006','HC-1009','100.00','CAPTURED','USD','2026-11-02'),
('PAY-007','HC-1012','250.00','CAPTURED','USD','2026-11-03'),
('PAY-008','HC-1013','100.00','CAPTURED','USD','2026-11-03'),
('PAY-008','HC-1013','100.00','CAPTURED','USD','2026-11-03'), # dup ID should NOT be double-counted
]
SETTLEMENTS = [
# settlement id, reservation id, amount, state, currency, settled_at
('SET-001','HC-1002','425.00','SETTLED','USD','2026-11-04'),
('SET-002','HC-1005','290.00','SETTLED','USD','2026-11-04'),
('SET-003','HC-1008','0.00','PENDING','USD','2026-11-05'),
('SET-004','HC-1010','255.00','SETTLED','USD','2026-11-05'),
('SET-005','HC-1014','150.00','SETTLED','USD','2026-11-05'),
]
COLUMNS = {
 'reservations.csv':['reservation_id','property_id','channel','payment_responsibility','booking_status','gross_amount','approved_refund','adjustment','ota_commission','currency','response_deadline'],
 'payments.csv':['payment_id','reservation_id','amount','status','currency','processed_at'],
 'settlements.csv':['settlement_id','reservation_id','amount','status','currency','settled_at'],
}

def create_data(directory: str | Path) -> None:
    base=Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    for file, rows in [('reservations.csv',RESERVATIONS),('payments.csv',PAYMENTS),('settlements.csv',SETTLEMENTS)]:
        with (base/file).open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f)
            writer.writerow(COLUMNS[file]);writer.writerows(rows)

if __name__=='__main__':
    create_data(Path(__file__).resolve().parents[1]/'data')
