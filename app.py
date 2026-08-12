from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file
)

from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime
from dotenv import load_dotenv

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm

import os
import io
import uuid


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "invoice-secret-key"
)

app.config["MONGO_URI"] = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017/invoice_generator"
)

mongo = PyMongo(app)


# =========================================================
# COMPANY BRANDING
# =========================================================

COMPANY_NAME = "LOGIXIUS"

COMPANY_TAGLINE = (
    "Transforming Ideas into Intelligent Solutions"
)


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def money(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def get_paid_amount(invoice):
    """
    Calculate total amount received
    from all payments.
    """

    payments = invoice.get(
        "payments",
        []
    )

    total_paid = 0.0

    for payment in payments:

        total_paid += money(
            payment.get(
                "amount",
                0
            )
        )

    return money(total_paid)


def get_remaining_amount(invoice):
    """
    Calculate remaining invoice amount.
    """

    grand_total = money(
        invoice.get(
            "grand_total",
            0
        )
    )

    paid_amount = get_paid_amount(
        invoice
    )

    return money(
        max(
            0,
            grand_total - paid_amount
        )
    )


def update_invoice_payment_status(invoice_id):
    """
    Update paid amount,
    remaining amount and
    payment status.
    """

    invoice = mongo.db.invoices.find_one({
        "_id": ObjectId(invoice_id)
    })

    if not invoice:
        return

    grand_total = money(
        invoice.get(
            "grand_total",
            0
        )
    )

    paid_amount = get_paid_amount(
        invoice
    )

    remaining_amount = money(
        max(
            0,
            grand_total - paid_amount
        )
    )

    if (
        paid_amount >= grand_total
        and grand_total > 0
    ):

        status = "Paid"

    elif paid_amount > 0:

        status = "Partially Paid"

    else:

        status = "Pending"

    mongo.db.invoices.update_one(

        {
            "_id": ObjectId(invoice_id)
        },

        {
            "$set": {

                "paid_amount":
                    paid_amount,

                "remaining_amount":
                    remaining_amount,

                "payment_status":
                    status
            }
        }
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def dashboard():

    invoices = list(
        mongo.db.invoices
        .find()
        .sort(
            "created_at",
            -1
        )
        .limit(5)
    )

    customers = (
        mongo.db.customers
        .count_documents({})
    )

    products = (
        mongo.db.products
        .count_documents({})
    )

    invoice_count = (
        mongo.db.invoices
        .count_documents({})
    )

    total_billing = 0.0
    total_paid = 0.0
    total_remaining = 0.0

    all_invoices = (
        mongo.db.invoices.find()
    )

    for invoice in all_invoices:

        grand_total = money(
            invoice.get(
                "grand_total",
                0
            )
        )

        paid = get_paid_amount(
            invoice
        )

        remaining = money(
            max(
                0,
                grand_total - paid
            )
        )

        total_billing += grand_total
        total_paid += paid
        total_remaining += remaining

    return render_template(

        "dashboard.html",

        invoices=invoices,

        customers=customers,

        products=products,

        invoice_count=invoice_count,

        revenue=money(
            total_paid
        ),

        total_billing=money(
            total_billing
        ),

        total_paid=money(
            total_paid
        ),

        total_remaining=money(
            total_remaining
        )
    )


# =========================================================
# CUSTOMERS
# =========================================================

@app.route(
    "/customers",
    methods=["GET", "POST"]
)
def customers():

    if request.method == "POST":

        mongo.db.customers.insert_one({

            "name":
                request.form.get(
                    "name",
                    ""
                ),

            "phone":
                request.form.get(
                    "phone",
                    ""
                ),

            "email":
                request.form.get(
                    "email",
                    ""
                ),

            "address":
                request.form.get(
                    "address",
                    ""
                ),

            "gstin":
                request.form.get(
                    "gstin",
                    ""
                ),

            "created_at":
                datetime.now()
        })

        flash(
            "Customer added successfully.",
            "success"
        )

        return redirect(
            url_for("customers")
        )

    data = list(
        mongo.db.customers
        .find()
        .sort(
            "created_at",
            -1
        )
    )

    return render_template(
        "customers.html",
        customers=data
    )


@app.route(
    "/customers/delete/<id>"
)
def delete_customer(id):

    mongo.db.customers.delete_one({
        "_id": ObjectId(id)
    })

    flash(
        "Customer deleted.",
        "success"
    )

    return redirect(
        url_for("customers")
    )


# =========================================================
# PRODUCTS
# =========================================================

@app.route(
    "/products",
    methods=["GET", "POST"]
)
def products():

    if request.method == "POST":

        mongo.db.products.insert_one({

            "name":
                request.form.get(
                    "name",
                    ""
                ),

            "price":
                money(
                    request.form.get(
                        "price",
                        0
                    )
                ),

            "tax":
                money(
                    request.form.get(
                        "tax",
                        18
                    )
                ),

            "created_at":
                datetime.now()
        })

        flash(
            "Product added successfully.",
            "success"
        )

        return redirect(
            url_for("products")
        )

    data = list(
        mongo.db.products
        .find()
        .sort(
            "created_at",
            -1
        )
    )

    return render_template(
        "products.html",
        products=data
    )


@app.route(
    "/products/delete/<id>"
)
def delete_product(id):

    mongo.db.products.delete_one({
        "_id": ObjectId(id)
    })

    flash(
        "Product deleted.",
        "success"
    )

    return redirect(
        url_for("products")
    )


# =========================================================
# INVOICE LIST
# =========================================================

@app.route("/invoices")
def invoices():

    data = list(
        mongo.db.invoices
        .find()
        .sort(
            "created_at",
            -1
        )
    )

    for invoice in data:

        paid_amount = get_paid_amount(
            invoice
        )

        remaining_amount = money(
            max(
                0,
                money(
                    invoice.get(
                        "grand_total",
                        0
                    )
                ) - paid_amount
            )
        )

        invoice["paid_amount"] = (
            paid_amount
        )

        invoice["remaining_amount"] = (
            remaining_amount
        )

    return render_template(
        "invoices.html",
        invoices=data
    )


# =========================================================
# CREATE INVOICE
# =========================================================

@app.route(
    "/invoice/create",
    methods=["GET", "POST"]
)
def create_invoice():

    if request.method == "POST":

        customer = {

            "name":
                request.form.get(
                    "customer_name",
                    ""
                ),

            "phone":
                request.form.get(
                    "customer_phone",
                    ""
                ),

            "email":
                request.form.get(
                    "customer_email",
                    ""
                ),

            "address":
                request.form.get(
                    "customer_address",
                    ""
                ),

            "gstin":
                request.form.get(
                    "customer_gstin",
                    ""
                )
        }

        names = request.form.getlist(
            "item_name[]"
        )

        qtys = request.form.getlist(
            "item_qty[]"
        )

        prices = request.form.getlist(
            "item_price[]"
        )

        taxes = request.form.getlist(
            "item_tax[]"
        )

        items = []

        subtotal = 0.0
        tax_total = 0.0

        for n, q, p, t in zip(
            names,
            qtys,
            prices,
            taxes
        ):

            if not n.strip():
                continue

            qty = money(q)
            price = money(p)
            tax = money(t)

            amount = money(
                qty * price
            )

            tax_amount = money(
                amount * tax / 100
            )

            subtotal += amount
            tax_total += tax_amount

            items.append({

                "name":
                    n.strip(),

                "quantity":
                    qty,

                "price":
                    price,

                "tax":
                    tax,

                "amount":
                    amount,

                "tax_amount":
                    tax_amount
            })

        discount = money(
            request.form.get(
                "discount",
                0
            )
        )

        taxable = max(
            0,
            subtotal - discount
        )

        tax_rate = (
            tax_total / subtotal * 100
            if subtotal > 0
            else 0
        )

        final_tax = money(
            taxable * tax_rate / 100
        )

        total = money(
            taxable + final_tax
        )

        invoice = {

            "invoice_number":
                request.form.get(
                    "invoice_number",
                    ""
                ),

            "date":
                request.form.get(
                    "date",
                    datetime.now().strftime(
                        "%Y-%m-%d"
                    )
                ),

            "due_date":
                request.form.get(
                    "due_date",
                    ""
                ),

            "customer":
                customer,

            "items":
                items,

            "subtotal":
                money(subtotal),

            "discount":
                discount,

            "taxable":
                money(taxable),

            "tax":
                final_tax,

            "grand_total":
                total,

            "payment_status":
                "Pending",

            "paid_amount":
                0.0,

            "remaining_amount":
                total,

            "payments":
                [],

            "notes":
                request.form.get(
                    "notes",
                    ""
                ),

            "created_at":
                datetime.now()
        }

        result = (
            mongo.db.invoices
            .insert_one(invoice)
        )

        flash(
            "Invoice created successfully.",
            "success"
        )

        return redirect(
            url_for(
                "invoice_view",
                invoice_id=str(
                    result.inserted_id
                )
            )
        )

    products = list(
        mongo.db.products
        .find()
        .sort(
            "name",
            1
        )
    )

    customers = list(
        mongo.db.customers
        .find()
        .sort(
            "name",
            1
        )
    )

    next_no = (
        mongo.db.invoices
        .count_documents({})
        + 1
    )

    return render_template(

        "create_invoice.html",

        products=products,

        customers=customers,

        next_no=
            f"INV-{datetime.now().year}-{next_no:04d}"
    )


# =========================================================
# EDIT INVOICE
# =========================================================

@app.route(
    "/invoice/edit/<invoice_id>",
    methods=["GET", "POST"]
)
def edit_invoice(invoice_id):

    invoice = mongo.db.invoices.find_one({

        "_id":
            ObjectId(invoice_id)

    })

    if not invoice:

        flash(
            "Invoice not found.",
            "danger"
        )

        return redirect(
            url_for("invoices")
        )

    if request.method == "POST":

        customer = {

            "name":
                request.form.get(
                    "customer_name",
                    ""
                ),

            "phone":
                request.form.get(
                    "customer_phone",
                    ""
                ),

            "email":
                request.form.get(
                    "customer_email",
                    ""
                ),

            "address":
                request.form.get(
                    "customer_address",
                    ""
                ),

            "gstin":
                request.form.get(
                    "customer_gstin",
                    ""
                )
        }

        names = request.form.getlist(
            "item_name[]"
        )

        qtys = request.form.getlist(
            "item_qty[]"
        )

        prices = request.form.getlist(
            "item_price[]"
        )

        taxes = request.form.getlist(
            "item_tax[]"
        )

        items = []

        subtotal = 0.0
        tax_total = 0.0

        for n, q, p, t in zip(
            names,
            qtys,
            prices,
            taxes
        ):

            if not n.strip():
                continue

            qty = money(q)
            price = money(p)
            tax = money(t)

            amount = money(
                qty * price
            )

            tax_amount = money(
                amount * tax / 100
            )

            subtotal += amount
            tax_total += tax_amount

            items.append({

                "name":
                    n.strip(),

                "quantity":
                    qty,

                "price":
                    price,

                "tax":
                    tax,

                "amount":
                    amount,

                "tax_amount":
                    tax_amount
            })

        discount = money(
            request.form.get(
                "discount",
                0
            )
        )

        taxable = max(
            0,
            subtotal - discount
        )

        tax_rate = (
            tax_total / subtotal * 100
            if subtotal > 0
            else 0
        )

        final_tax = money(
            taxable * tax_rate / 100
        )

        grand_total = money(
            taxable + final_tax
        )

        # KEEP EXISTING PAYMENTS

        payments = invoice.get(
            "payments",
            []
        )

        paid_amount = 0.0

        for payment in payments:

            paid_amount += money(
                payment.get(
                    "amount",
                    0
                )
            )

        paid_amount = money(
            paid_amount
        )

        remaining_amount = money(
            max(
                0,
                grand_total - paid_amount
            )
        )

        # STATUS

        if (
            paid_amount >= grand_total
            and grand_total > 0
        ):

            payment_status = "Paid"

        elif paid_amount > 0:

            payment_status = "Partially Paid"

        else:

            payment_status = "Pending"

        # UPDATE DATABASE

        mongo.db.invoices.update_one(

            {
                "_id":
                    ObjectId(invoice_id)
            },

            {
                "$set": {

                    "invoice_number":
                        request.form.get(
                            "invoice_number",
                            invoice.get(
                                "invoice_number",
                                ""
                            )
                        ),

                    "date":
                        request.form.get(
                            "date",
                            invoice.get(
                                "date",
                                ""
                            )
                        ),

                    "due_date":
                        request.form.get(
                            "due_date",
                            ""
                        ),

                    "customer":
                        customer,

                    "items":
                        items,

                    "subtotal":
                        money(subtotal),

                    "discount":
                        discount,

                    "taxable":
                        money(taxable),

                    "tax":
                        final_tax,

                    "grand_total":
                        grand_total,

                    "paid_amount":
                        paid_amount,

                    "remaining_amount":
                        remaining_amount,

                    "payment_status":
                        payment_status,

                    "notes":
                        request.form.get(
                            "notes",
                            ""
                        ),

                    "updated_at":
                        datetime.now()
                }
            }
        )

        flash(
            "Invoice updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "invoice_view",
                invoice_id=invoice_id
            )
        )

    return render_template(
        "edit_invoice.html",
        invoice=invoice
    )


# =========================================================
# VIEW INVOICE
# =========================================================

@app.route(
    "/invoice/<invoice_id>"
)
def invoice_view(invoice_id):

    invoice = mongo.db.invoices.find_one({

        "_id":
            ObjectId(invoice_id)

    })

    if not invoice:

        flash(
            "Invoice not found.",
            "danger"
        )

        return redirect(
            url_for("invoices")
        )

    paid_amount = get_paid_amount(
        invoice
    )

    remaining_amount = (
        get_remaining_amount(
            invoice
        )
    )

    mongo.db.invoices.update_one(

        {
            "_id":
                ObjectId(invoice_id)
        },

        {
            "$set": {

                "paid_amount":
                    paid_amount,

                "remaining_amount":
                    remaining_amount
            }
        }
    )

    invoice["paid_amount"] = (
        paid_amount
    )

    invoice["remaining_amount"] = (
        remaining_amount
    )

    now_date = datetime.now().strftime(
        "%Y-%m-%d"
    )

    return render_template(

        "invoice.html",

        invoice=invoice,

        now_date=now_date
    )


# =========================================================
# ADD PAYMENT
# =========================================================

@app.route(
    "/invoice/<invoice_id>/payment",
    methods=["POST"]
)
def add_payment(invoice_id):

    invoice = mongo.db.invoices.find_one({

        "_id":
            ObjectId(invoice_id)

    })

    if not invoice:

        flash(
            "Invoice not found.",
            "danger"
        )

        return redirect(
            url_for("invoices")
        )

    grand_total = money(
        invoice.get(
            "grand_total",
            0
        )
    )

    already_paid = get_paid_amount(
        invoice
    )

    remaining = money(
        max(
            0,
            grand_total - already_paid
        )
    )

    payment_amount = money(
        request.form.get(
            "amount",
            0
        )
    )

    if payment_amount <= 0:

        flash(
            "Payment amount must be greater than zero.",
            "danger"
        )

        return redirect(
            url_for(
                "invoice_view",
                invoice_id=invoice_id
            )
        )

    if payment_amount > remaining:

        flash(
            f"Payment cannot exceed remaining amount ₹{remaining:.2f}.",
            "danger"
        )

        return redirect(
            url_for(
                "invoice_view",
                invoice_id=invoice_id
            )
        )

    payment_type = request.form.get(
        "payment_type",
        "Advance"
    )

    payment_date = request.form.get(
        "payment_date",
        datetime.now().strftime(
            "%Y-%m-%d"
        )
    )

    payment_note = request.form.get(
        "payment_note",
        ""
    )

    new_remaining = money(
        remaining - payment_amount
    )

    if new_remaining <= 0:

        payment_type = "Final Payment"

    payment = {

        "id":
            str(uuid.uuid4()),

        "date":
            payment_date,

        "amount":
            payment_amount,

        "type":
            payment_type,

        "note":
            payment_note,

        "remaining":
            new_remaining,

        "created_at":
            datetime.now()
    }

    mongo.db.invoices.update_one(

        {
            "_id":
                ObjectId(invoice_id)
        },

        {
            "$push": {

                "payments":
                    payment
            }
        }
    )

    update_invoice_payment_status(
        invoice_id
    )

    flash(
        f"{payment_type} of ₹{payment_amount:.2f} recorded successfully.",
        "success"
    )

    return redirect(
        url_for(
            "invoice_view",
            invoice_id=invoice_id
        )
    )


# =========================================================
# PAYMENT PDF
# =========================================================

@app.route(
    "/invoice/<invoice_id>/payment/<payment_id>/pdf"
)
def payment_pdf(
    invoice_id,
    payment_id
):

    invoice = mongo.db.invoices.find_one({

        "_id":
            ObjectId(invoice_id)

    })

    if not invoice:
        return "Invoice not found", 404

    payment = None

    for p in invoice.get(
        "payments",
        []
    ):

        if p.get("id") == payment_id:

            payment = p
            break

    if not payment:
        return "Payment not found", 404

    buffer = io.BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    width, height = A4

    left = 20 * mm

    # =====================================================
    # HEADER
    # =====================================================

    c.setFillColor(
        colors.HexColor(
            "#172554"
        )
    )

    c.rect(
        0,
        height - 45 * mm,
        width,
        45 * mm,
        fill=1,
        stroke=0
    )

    c.setFillColor(
        colors.white
    )

    # COMPANY NAME

    c.setFont(
        "Helvetica-Bold",
        24
    )

    c.drawString(
        left,
        height - 16 * mm,
        COMPANY_NAME
    )

    # TAGLINE

    c.setFont(
        "Helvetica-Bold",
        8
    )

    c.drawString(
        left,
        height - 23 * mm,
        COMPANY_TAGLINE
    )

    # TITLE

    c.setFont(
        "Helvetica-Bold",
        15
    )

    c.drawString(
        left,
        height - 34 * mm,
        "PAYMENT RECEIPT"
    )

    # INVOICE NUMBER

    c.setFont(
        "Helvetica",
        10
    )

    c.drawRightString(
        width - left,
        height - 18 * mm,
        invoice.get(
            "invoice_number",
            ""
        )
    )

    y = height - 60 * mm

    # =====================================================
    # PAYMENT DETAILS
    # =====================================================

    c.setFillColor(
        colors.black
    )

    c.setFont(
        "Helvetica-Bold",
        12
    )

    c.drawString(
        left,
        y,
        "Payment Details"
    )

    y -= 10 * mm

    details = [

        (
            "Invoice Number",
            invoice.get(
                "invoice_number",
                ""
            )
        ),

        (
            "Payment Date",
            payment.get(
                "date",
                ""
            )
        ),

        (
            "Payment Type",
            payment.get(
                "type",
                ""
            )
        ),

        (
            "Customer",
            invoice.get(
                "customer",
                {}
            ).get(
                "name",
                ""
            )
        )
    ]

    for label, value in details:

        c.setFont(
            "Helvetica-Bold",
            10
        )

        c.drawString(
            left,
            y,
            f"{label}:"
        )

        c.setFont(
            "Helvetica",
            10
        )

        c.drawString(
            left + 40 * mm,
            y,
            str(value)
        )

        y -= 7 * mm

    # =====================================================
    # PAYMENT SUMMARY
    # =====================================================

    y -= 5 * mm

    c.setFillColor(
        colors.HexColor(
            "#f1f5f9"
        )
    )

    c.roundRect(
        left,
        y - 45 * mm,
        width - 2 * left,
        42 * mm,
        4 * mm,
        fill=1,
        stroke=0
    )

    c.setFillColor(
        colors.black
    )

    c.setFont(
        "Helvetica-Bold",
        12
    )

    c.drawString(
        left + 7 * mm,
        y - 10 * mm,
        "Payment Summary"
    )

    c.setFont(
        "Helvetica",
        11
    )

    c.drawString(
        left + 7 * mm,
        y - 20 * mm,
        "Invoice Total"
    )

    c.drawRightString(
        width - left - 7 * mm,
        y - 20 * mm,
        f"Rs. {money(invoice.get('grand_total', 0)):.2f}"
    )

    c.drawString(
        left + 7 * mm,
        y - 29 * mm,
        "Payment Received"
    )

    c.drawRightString(
        width - left - 7 * mm,
        y - 29 * mm,
        f"Rs. {money(payment.get('amount', 0)):.2f}"
    )

    c.setFont(
        "Helvetica-Bold",
        11
    )

    c.drawString(
        left + 7 * mm,
        y - 38 * mm,
        "Remaining Amount"
    )

    c.drawRightString(
        width - left - 7 * mm,
        y - 38 * mm,
        f"Rs. {money(payment.get('remaining', 0)):.2f}"
    )

    # =====================================================
    # FOOTER
    # =====================================================

    c.setFont(
        "Helvetica-Bold",
        10
    )

    c.drawCentredString(
        width / 2,
        25 * mm,
        COMPANY_NAME
    )

    c.setFont(
        "Helvetica-Oblique",
        8
    )

    c.drawCentredString(
        width / 2,
        18 * mm,
        COMPANY_TAGLINE
    )

    c.setFont(
        "Helvetica",
        8
    )

    c.drawCentredString(
        width / 2,
        12 * mm,
        "Thank you for your payment!"
    )

    c.save()

    buffer.seek(0)

    safe_type = payment.get(
        "type",
        "Payment"
    ).replace(
        " ",
        "_"
    )

    return send_file(

        buffer,

        as_attachment=True,

        download_name=(

            f"{invoice['invoice_number']}_"
            f"{safe_type}_"
            f"{payment_id[:8]}.pdf"
        ),

        mimetype="application/pdf"
    )


# =========================================================
# MAIN INVOICE PDF
# =========================================================

@app.route(
    "/invoice/pdf/<invoice_id>"
)
def invoice_pdf(invoice_id):

    inv = mongo.db.invoices.find_one({

        "_id":
            ObjectId(invoice_id)

    })

    if not inv:

        return "Invoice not found", 404

    buffer = io.BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    width, height = A4

    left = 20 * mm

    y = height - 22 * mm

    # =====================================================
    # HEADER
    # =====================================================

    c.setFillColor(
        colors.HexColor(
            "#172554"
        )
    )

    c.rect(
        0,
        height - 45 * mm,
        width,
        45 * mm,
        fill=1,
        stroke=0
    )

    c.setFillColor(
        colors.white
    )

    # COMPANY NAME

    c.setFont(
        "Helvetica-Bold",
        22
    )

    c.drawString(
        left,
        height - 16 * mm,
        COMPANY_NAME
    )

    # TAGLINE

    c.setFont(
        "Helvetica-Bold",
        8
    )

    c.drawString(
        left,
        height - 23 * mm,
        COMPANY_TAGLINE
    )

    # INVOICE TITLE

    c.setFont(
        "Helvetica-Bold",
        15
    )

    c.drawString(
        left,
        height - 34 * mm,
        "INVOICE"
    )

    # INVOICE NUMBER

    c.setFont(
        "Helvetica",
        10
    )

    c.drawRightString(
        width - left,
        height - 17 * mm,
        inv.get(
            "invoice_number",
            ""
        )
    )

    # DATE

    c.drawRightString(
        width - left,
        height - 23 * mm,
        inv.get(
            "date",
            ""
        )
    )

    y = height - 58 * mm

    # =====================================================
    # BILL TO
    # =====================================================

    c.setFillColor(
        colors.black
    )

    c.setFont(
        "Helvetica-Bold",
        11
    )

    c.drawString(
        left,
        y,
        "Bill To"
    )

    y -= 6 * mm

    cust = inv.get(
        "customer",
        {}
    )

    customer_lines = [

        cust.get(
            "name",
            ""
        ),

        cust.get(
            "address",
            ""
        ),

        cust.get(
            "phone",
            ""
        ),

        cust.get(
            "email",
            ""
        ),

        cust.get(
            "gstin",
            ""
        )
    ]

    c.setFont(
        "Helvetica",
        10
    )

    for line in customer_lines:

        if line:

            c.drawString(
                left,
                y,
                str(line)[:80]
            )

            y -= 5 * mm

    # =====================================================
    # ITEMS TABLE
    # =====================================================

    y -= 5 * mm

    c.setFillColor(
        colors.HexColor(
            "#e5e7eb"
        )
    )

    c.rect(
        left,
        y - 6 * mm,
        width - 2 * left,
        8 * mm,
        fill=1,
        stroke=0
    )

    c.setFillColor(
        colors.black
    )

    c.setFont(
        "Helvetica-Bold",
        9
    )

    c.drawString(
        left + 2 * mm,
        y - 3 * mm,
        "Item"
    )

    c.drawRightString(
        width - 75 * mm,
        y - 3 * mm,
        "Qty"
    )

    c.drawRightString(
        width - 45 * mm,
        y - 3 * mm,
        "Price"
    )

    c.drawRightString(
        width - left,
        y - 3 * mm,
        "Amount"
    )

    y -= 11 * mm

    c.setFont(
        "Helvetica",
        9
    )

    for item in inv.get(
        "items",
        []
    ):

        c.drawString(
            left + 2 * mm,
            y,
            str(
                item.get(
                    "name",
                    ""
                )
            )[:45]
        )

        c.drawRightString(
            width - 75 * mm,
            y,
            str(
                item.get(
                    "quantity",
                    0
                )
            )
        )

        c.drawRightString(
            width - 45 * mm,
            y,
            f"Rs. {money(item.get('price', 0)):.2f}"
        )

        c.drawRightString(
            width - left,
            y,
            f"Rs. {money(item.get('amount', 0)):.2f}"
        )

        y -= 6 * mm

    # =====================================================
    # TOTALS
    # =====================================================

    y -= 4 * mm

    c.line(
        width - 80 * mm,
        y,
        width - left,
        y
    )

    total_rows = [

        (
            "Subtotal",
            money(
                inv.get(
                    "subtotal",
                    0
                )
            )
        ),

        (
            "Discount",
            money(
                inv.get(
                    "discount",
                    0
                )
            )
        ),

        (
            "Tax",
            money(
                inv.get(
                    "tax",
                    0
                )
            )
        ),

        (
            "Grand Total",
            money(
                inv.get(
                    "grand_total",
                    0
                )
            )
        )
    ]

    for label, value in total_rows:

        y -= 6 * mm

        c.setFont(

            "Helvetica-Bold"
            if label == "Grand Total"
            else "Helvetica",

            10
        )

        c.drawString(
            width - 80 * mm,
            y,
            label
        )

        c.drawRightString(
            width - left,
            y,
            f"Rs. {value:.2f}"
        )

    # =====================================================
    # PAYMENT SUMMARY
    # =====================================================

    y -= 12 * mm

    paid_amount = get_paid_amount(
        inv
    )

    remaining_amount = max(

        0,

        money(
            inv.get(
                "grand_total",
                0
            )
        ) - paid_amount

    )

    c.setFont(
        "Helvetica-Bold",
        10
    )

    c.drawString(
        left,
        y,
        "Payment Summary"
    )

    y -= 6 * mm

    c.setFont(
        "Helvetica",
        9
    )

    c.drawString(
        left,
        y,
        f"Total Amount: Rs. "
        f"{money(inv.get('grand_total', 0)):.2f}"
    )

    y -= 5 * mm

    c.drawString(
        left,
        y,
        f"Paid Amount: Rs. "
        f"{paid_amount:.2f}"
    )

    y -= 5 * mm

    c.drawString(
        left,
        y,
        f"Remaining Amount: Rs. "
        f"{remaining_amount:.2f}"
    )

    y -= 5 * mm

    c.drawString(
        left,
        y,
        f"Payment Status: "
        f"{inv.get('payment_status', 'Pending')}"
    )

    # =====================================================
    # PAYMENT HISTORY
    # =====================================================

    if inv.get("payments"):

        y -= 10 * mm

        c.setFont(
            "Helvetica-Bold",
            10
        )

        c.drawString(
            left,
            y,
            "Payment History"
        )

        y -= 6 * mm

        c.setFont(
            "Helvetica",
            8
        )

        for index, payment in enumerate(

            inv.get(
                "payments",
                []
            ),

            start=1
        ):

            text = (

                f"{index}. "

                f"{payment.get('date', '')} | "

                f"{payment.get('type', '')} | "

                f"Rs. "
                f"{money(payment.get('amount', 0)):.2f} | "

                f"Remaining: Rs. "
                f"{money(payment.get('remaining', 0)):.2f}"
            )

            c.drawString(
                left,
                y,
                text[:120]
            )

            y -= 5 * mm

    # =====================================================
    # NOTES
    # =====================================================

    if inv.get("notes"):

        y -= 5 * mm

        c.setFont(
            "Helvetica-Bold",
            9
        )

        c.drawString(
            left,
            y,
            "Notes:"
        )

        c.setFont(
            "Helvetica",
            9
        )

        c.drawString(
            left + 15 * mm,
            y,
            str(
                inv["notes"]
            )[:100]
        )

    # =====================================================
    # FOOTER
    # =====================================================

    c.setFont(
        "Helvetica-Bold",
        9
    )

    c.drawCentredString(
        width / 2,
        18 * mm,
        COMPANY_NAME
    )

    c.setFont(
        "Helvetica-Oblique",
        8
    )

    c.drawCentredString(
        width / 2,
        12 * mm,
        COMPANY_TAGLINE
    )

    c.setFont(
        "Helvetica",
        8
    )

    c.drawCentredString(
        width / 2,
        7 * mm,
        "Thank you for your business!"
    )

    c.save()

    buffer.seek(0)

    return send_file(

        buffer,

        as_attachment=True,

        download_name=(

            f"{inv['invoice_number']}.pdf"
        ),

        mimetype="application/pdf"
    )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )