"""Create human-readable PDF investigation packet; no real customer data."""
from io import BytesIO
from datetime import datetime,timezone
import json
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from .reconciliation import money,Case

def build_packet(case:Case, investigation:dict, audit:list[dict], review_state:str='OPEN')->bytes:
    output=BytesIO();styles=getSampleStyleSheet()
    doc=SimpleDocTemplate(output,pagesize=(612,792),rightMargin=43,leftMargin=43,topMargin=40,bottomMargin=40,title=f'HotelCase {case.reservation_id}')
    story=[Paragraph('HotelCase AI | Investigation Evidence Packet',styles['Title']),
           Paragraph('SYNTHETIC DEMO DATA — NOT A REAL DISPUTE FILING',styles['Heading3']),
           Paragraph(f"Generated (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",styles['Normal']),Spacer(1,14)]
    fields=[('Reservation ID',case.reservation_id),('Property',case.property_id),('Channel',case.channel),('Payment responsibility',case.payment_responsibility),('Booking status',case.booking_status),('Category',case.category),('Review state',review_state),('Expected',money(case.expected_cents)),('Confirmed received',money(case.received_cents)),('Difference',money(case.discrepancy_cents)),('Reference date, unverified',case.response_deadline or 'Not supplied')]
    table=Table([[Paragraph(escape(k),styles['BodyText']),Paragraph(escape(v),styles['BodyText'])] for k,v in fields],colWidths=[190,330],hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),colors.HexColor('#e8edf3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),0.3,colors.lightgrey),('LEFTPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.extend([table,Spacer(1,12),Paragraph('Agent conclusion',styles['Heading2'])])
    for entry in [investigation.get('recommendation','Not investigated'),investigation.get('next_step',''),investigation.get('explanation','')]:
        if entry:story.append(Paragraph(escape(str(entry)),styles['BodyText']));story.append(Spacer(1,5))
    story.append(Paragraph('Deterministic checks',styles['Heading2']))
    for entry in investigation.get('checks',[]):story.append(Paragraph('• '+escape(str(entry)),styles['BodyText']))
    for label,key in [('Payment source records','payment_rows'),('OTA settlement source records','settlement_rows')]:
        story.extend([Spacer(1,9),Paragraph(label,styles['Heading2'])])
        records=investigation.get(key,[])
        if not records:story.append(Paragraph('No records found',styles['BodyText']))
        for record in records:
            story.append(Paragraph(escape(json.dumps(record,sort_keys=True)),styles['BodyText']));story.append(Spacer(1,4))
    story.append(Paragraph('Case audit history',styles['Heading2']))
    for item in audit[:30]:
        story.append(Paragraph(escape(f"{item['created_at']} | {item['action']} | {item['actor']} | {item['detail']}")[:2000],styles['BodyText']));story.append(Spacer(1,5))
    story.extend([Spacer(1,14),Paragraph('Limitations and approval',styles['Heading2']),Paragraph('The data and policies in this demonstration are fictional. A detected ledger difference is not proof of recoverable revenue. Verify supporting documents, contracts, timelines, accounting treatment, payment provider rules, and consumer protection requirements. No claim was submitted, no payment was charged, and no external system was updated.',styles['BodyText'])])
    doc.build(story)
    return output.getvalue()
