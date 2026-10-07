from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    jsonify
)

from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime
from dotenv import load_dotenv

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

import os
import io
import uuid
import json


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

LOGO_PATH = os.path.join(
    app.root_path,
    "static",
    "images",
    "logo_logixius1.png"
)


# =========================================================
# GST / E-INVOICE CONFIGURATION
# =========================================================
#
# IMPORTANT:
#
# Put your actual company GST details in .env
#
# Example:
#
# SELLER_GSTIN=27XXXXXXXXXX1Z5
# SELLER_LEGAL_NAME=LOGIXIUS
# SELLER_TRADE_NAME=LOGIXIUS
# SELLER_ADDRESS1=Your Business Address
# SELLER_ADDRESS2=
# SELLER_LOCATION=NAGPUR
# SELLER_PINCODE=440001
# SELLER_STATE_CODE=27
# SELLER_STATE_NAME=Maharashtra
# SELLER_PHONE=9876543210
# SELLER_EMAIL=example@gmail.com
#
# DO NOT use example GSTIN for actual GST submission.
#

SELLER_GSTIN = os.getenv(
    "SELLER_GSTIN",
    ""
).strip()

SELLER_LEGAL_NAME = os.getenv(
    "SELLER_LEGAL_NAME",
    COMPANY_NAME
).strip()

SELLER_TRADE_NAME = os.getenv(
    "SELLER_TRADE_NAME",
    COMPANY_NAME
).strip()

SELLER_ADDRESS1 = os.getenv(
    "SELLER_ADDRESS1",
    ""
).strip()

SELLER_ADDRESS2 = os.getenv(
    "SELLER_ADDRESS2",
    ""
).strip()

SELLER_LOCATION = os.getenv(
    "SELLER_LOCATION",
    ""
).strip()

SELLER_PINCODE = os.getenv(
    "SELLER_PINCODE",
    ""
).strip()

SELLER_STATE_CODE = os.getenv(
    "SELLER_STATE_CODE",
    ""
).strip()

SELLER_STATE_NAME = os.getenv(
    "SELLER_STATE_NAME",
    ""
).strip()

SELLER_PHONE = os.getenv(
    "SELLER_PHONE",
    ""
).strip()

SELLER_EMAIL = os.getenv(
    "SELLER_EMAIL",
    ""
).strip()


# =========================================================
# GST HELPERS
# =========================================================

def get_state_code_from_gstin(gstin):
    """
    First two digits of a GSTIN represent
    the state code.

    Example:
    27XXXXXXXXXX1Z5 -> 27
    """

    gstin = str(gstin or "").strip()

    if len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]

    return ""


def get_customer_state_code(customer):
    """
    Get buyer state code.

    Priority:
    1. customer state_code
    2. customer GSTIN first two digits
    """

    state_code = str(
        customer.get(
            "state_code",
            ""
        ) or ""
    ).strip()

    if state_code:
        return state_code

    return get_state_code_from_gstin(
        customer.get(
            "gstin",
            ""
        )
    )


def calculate_gst_for_invoice(invoice):
    """
    Calculate GST split for e-invoice JSON.

    If seller and buyer are in the same state:
        CGST + SGST

    If seller and buyer are in different states:
        IGST
    """

    seller_state = str(
        SELLER_STATE_CODE or ""
    ).strip()

    customer = invoice.get(
        "customer",
        {}
    )

    buyer_state = get_customer_state_code(
        customer
    )

    total_tax = money(
        invoice.get(
            "tax",
            0
        )
    )

    if (
        seller_state
        and buyer_state
        and seller_state == buyer_state
    ):

        cgst = money(
            total_tax / 2
        )

        sgst = money(
            total_tax - cgst
        )

        igst = 0.0

    else:

        cgst = 0.0
        sgst = 0.0
        igst = total_tax

    return {
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst
    }


# =========================================================
# GST JSON GENERATOR
# =========================================================

def generate_gst_einvoice_json(invoice):
    """
    Generate GST e-Invoice INV-01 style JSON.

    This creates the source JSON required for
    e-Invoice reporting.

    IMPORTANT:
    Actual GST portal/IRP validation requires
    all applicable mandatory fields and correct
    taxpayer information.
    """

    customer = invoice.get(
        "customer",
        {}
    )

    items = invoice.get(
        "items",
        []
    )

    invoice_number = str(
        invoice.get(
            "invoice_number",
            ""
        )
    ).strip()

    invoice_date = str(
        invoice.get(
            "date",
            ""
        )
    ).strip()

    # -----------------------------------------------------
    # GSTIN
    # -----------------------------------------------------

    buyer_gstin = str(
        customer.get(
            "gstin",
            ""
        ) or ""
    ).strip()

    # -----------------------------------------------------
    # STATE
    # -----------------------------------------------------

    buyer_state_code = (
        get_customer_state_code(
            customer
        )
    )

    seller_state_code = (
        SELLER_STATE_CODE
    )

    # -----------------------------------------------------
    # TAX CALCULATION
    # -----------------------------------------------------

    gst_split = calculate_gst_for_invoice(
        invoice
    )

    cgst_total = gst_split["cgst"]
    sgst_total = gst_split["sgst"]
    igst_total = gst_split["igst"]

    # -----------------------------------------------------
    # SUPPLY TYPE
    # -----------------------------------------------------

    supply_type = (
        "B2B"
        if buyer_gstin
        else "B2C"
    )

    # -----------------------------------------------------
    # ITEM LIST
    # -----------------------------------------------------

    item_list = []

    calculated_taxable_total = 0.0
    calculated_tax_total = 0.0

    for index, item in enumerate(
        items,
        start=1
    ):

        quantity = money(
            item.get(
                "quantity",
                0
            )
        )

        unit_price = money(
            item.get(
                "price",
                0
            )
        )

        gross_amount = money(
            quantity * unit_price
        )

        item_discount = money(
            item.get(
                "discount",
                0
            )
        )

        taxable_value = money(
            max(
                0,
                gross_amount - item_discount
            )
        )

        gst_rate = money(
            item.get(
                "tax",
                0
            )
        )

        item_tax = money(
            taxable_value * gst_rate / 100
        )

        calculated_taxable_total += (
            taxable_value
        )

        calculated_tax_total += (
            item_tax
        )

        # -------------------------------------------------
        # GST SPLIT PER ITEM
        # -------------------------------------------------

        if (
            seller_state_code
            and buyer_state_code
            and seller_state_code == buyer_state_code
        ):

            item_cgst = money(
                item_tax / 2
            )

            item_sgst = money(
                item_tax - item_cgst
            )

            item_igst = 0.0

        else:

            item_cgst = 0.0
            item_sgst = 0.0
            item_igst = item_tax

        # -------------------------------------------------
        # HSN
        # -------------------------------------------------

        hsn_code = str(
            item.get(
                "hsn",
                item.get(
                    "hsn_code",
                    ""
                )
            ) or ""
        ).strip()

        # -------------------------------------------------
        # UQC
        # -------------------------------------------------

        unit = str(
            item.get(
                "unit",
                "NOS"
            ) or "NOS"
        ).strip().upper()

        # -------------------------------------------------
        # SERVICE
        # -------------------------------------------------

        is_service = str(
            item.get(
                "is_service",
                "N"
            ) or "N"
        ).upper()

        # -------------------------------------------------
        # ITEM JSON
        # -------------------------------------------------

        item_json = {

            "SlNo":
                str(index),

            "PrdDesc":
                str(
                    item.get(
                        "name",
                        ""
                    )
                )[:300],

            "IsServc":
                "Y"
                if is_service == "Y"
                else "N",

            "HsnCd":
                hsn_code,

            "Qty":
                quantity,

            "Unit":
                unit,

            "UnitPrice":
                unit_price,

            "TotAmt":
                gross_amount,

            "Discount":
                item_discount,

            "AssAmt":
                taxable_value,

            "GstRt":
                gst_rate,

            "IgstAmt":
                item_igst,

            "CgstAmt":
                item_cgst,

            "SgstAmt":
                item_sgst,

            "TotItemVal":
                money(
                    taxable_value
                    + item_tax
                )
        }

        item_list.append(
            item_json
        )

    # -----------------------------------------------------
    # TOTALS
    # -----------------------------------------------------

    taxable_value = money(
        invoice.get(
            "taxable",
            calculated_taxable_total
        )
    )

    total_invoice_value = money(
        invoice.get(
            "grand_total",
            taxable_value
            + calculated_tax_total
        )
    )

    discount_total = money(
        invoice.get(
            "discount",
            0
        )
    )

    # -----------------------------------------------------
    # BUYER STATE
    # -----------------------------------------------------

    buyer_state_name = str(
        customer.get(
            "state",
            ""
        ) or ""
    ).strip()

    buyer_location = str(
        customer.get(
            "location",
            customer.get(
                "city",
                ""
            )
        ) or ""
    ).strip()

    buyer_pincode = str(
        customer.get(
            "pincode",
            ""
        ) or ""
    ).strip()

    buyer_address = str(
        customer.get(
            "address",
            ""
        ) or ""
    ).strip()

    # -----------------------------------------------------
    # BUYER LEGAL NAME
    # -----------------------------------------------------

    buyer_name = str(
        customer.get(
            "name",
            ""
        )
    ).strip()

    # -----------------------------------------------------
    # MAIN GST JSON
    # -----------------------------------------------------

    gst_json = {

        "Version": "1.1",

        "TranDtls": {

            "TaxSch": "GST",

            "SupTyp":
                supply_type,

            "RegRev": "N",

            "IgstOnIntra":
                "N"
        },

        "DocDtls": {

            "Typ": "INV",

            "No":
                invoice_number,

            "Dt":
                datetime.strptime(
                    invoice_date,
                    "%Y-%m-%d"
                ).strftime(
                    "%d/%m/%Y"
                )
            if invoice_date
            else datetime.now().strftime(
                "%d/%m/%Y"
            )
        },

        "SellerDtls": {

            "Gstin":
                SELLER_GSTIN,

            "LglNm":
                SELLER_LEGAL_NAME,

            "TrdNm":
                SELLER_TRADE_NAME,

            "Addr1":
                SELLER_ADDRESS1,

            "Addr2":
                SELLER_ADDRESS2,

            "Loc":
                SELLER_LOCATION,

            "Pin":
                int(
                    SELLER_PINCODE
                )
                if SELLER_PINCODE.isdigit()
                else 0,

            "Stcd":
                seller_state_code,

            "Ph":
                SELLER_PHONE,

            "Em":
                SELLER_EMAIL
        },

        "BuyerDtls": {

            "Gstin":
                buyer_gstin
                if buyer_gstin
                else "URP",

            "LglNm":
                buyer_name,

            "TrdNm":
                buyer_name,

            "Pos":
                buyer_state_code,

            "Addr1":
                buyer_address,

            "Loc":
                buyer_location,

            "Pin":
                int(
                    buyer_pincode
                )
                if buyer_pincode.isdigit()
                else 0,

            "Stcd":
                buyer_state_code,

            "Ph":
                str(
                    customer.get(
                        "phone",
                        ""
                    ) or ""
                ),

            "Em":
                str(
                    customer.get(
                        "email",
                        ""
                    ) or ""
                )
        },

        "ItemList":
            item_list,

        "ValDtls": {

            "AssVal":
                taxable_value,

            "CgstVal":
                cgst_total,

            "SgstVal":
                sgst_total,

            "IgstVal":
                igst_total,

            "Discount":
                discount_total,

            "OthChrg":
                0.0,

            "RndOffAmt":
                0.0,

            "TotInvVal":
                total_invoice_value
        },

        "PayDtls": {

            "PaidAmt":
                money(
                    invoice.get(
                        "paid_amount",
                        get_paid_amount(
                            invoice
                        )
                    )
                ),

            "PaymtDue":
                money(
                    invoice.get(
                        "remaining_amount",
                        get_remaining_amount(
                            invoice
                        )
                    )
                )
        },

        "InvRm":
            str(
                invoice.get(
                    "notes",
                    ""
                ) or ""
            )
    }

    return gst_json


# =========================================================
# GST JSON DOWNLOAD
# =========================================================

@app.route(
    "/invoice/<invoice_id>/gst-json"
)
def invoice_gst_json(invoice_id):

    invoice = mongo.db.invoices.find_one({
        "_id":
            ObjectId(invoice_id)
    })

    if not invoice:

        return (
            "Invoice not found",
            404
        )

    try:

        gst_data = (
            generate_gst_einvoice_json(
                invoice
            )
        )

    except Exception as e:

        print(
            "GST JSON generation error:",
            e
        )

        return (
            f"Unable to generate GST JSON: {e}",
            500
        )

    # -----------------------------------------------------
    # CREATE JSON FILE
    # -----------------------------------------------------

    json_data = json.dumps(
        gst_data,
        indent=4,
        ensure_ascii=False
    )

    buffer = io.BytesIO(
        json_data.encode(
            "utf-8"
        )
    )

    buffer.seek(0)

    filename = (
        f"{invoice.get('invoice_number', 'invoice')}"
        f"_GST_EINVOICE.json"
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/json"
    )


# =========================================================
# GST JSON VIEW / API
# =========================================================

@app.route(
    "/invoice/<invoice_id>/gst-json/view"
)
def invoice_gst_json_view(invoice_id):

    invoice = mongo.db.invoices.find_one({
        "_id":
            ObjectId(invoice_id)
    })

    if not invoice:

        return (
            "Invoice not found",
            404
        )

    try:

        gst_data = (
            generate_gst_einvoice_json(
                invoice
            )
        )

    except Exception as e:

        return (
            jsonify({
                "success": False,
                "error": str(e)
            }),
            500
        )

    return jsonify(
        gst_data
    )


# =========================================================
# LOGO HELPER
# =========================================================

def get_logo_path():

    if os.path.exists(
        LOGO_PATH
    ):

        return LOGO_PATH

    return None


def draw_logo(
    canvas_obj,
    x,
    y,
    width,
    height,
    preserve_aspect_ratio=True
):

    logo_path = get_logo_path()

    if not logo_path:

        return False

    try:

        logo = ImageReader(
            logo_path
        )

        if preserve_aspect_ratio:

            image_width, image_height = (
                logo.getSize()
            )

            if (
                image_width <= 0
                or image_height <= 0
            ):

                return False

            scale = min(
                width / image_width,
                height / image_height
            )

            draw_width = (
                image_width * scale
            )

            draw_height = (
                image_height * scale
            )

            draw_x = (
                x
                + (
                    width
                    - draw_width
                ) / 2
            )

            draw_y = (
                y
                + (
                    height
                    - draw_height
                ) / 2
            )

        else:

            draw_x = x
            draw_y = y
            draw_width = width
            draw_height = height

        canvas_obj.drawImage(
            logo,
            draw_x,
            draw_y,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            mask="auto"
        )

        return True

    except Exception as e:

        print(
            "Logo could not be added to PDF:",
            e
        )

        return False


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def money(value):

    try:

        return round(
            float(value),
            2
        )

    except (
        TypeError,
        ValueError
    ):

        return 0.0


def get_paid_amount(invoice):

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

    return money(
        total_paid
    )


def get_remaining_amount(invoice):

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


def update_invoice_payment_status(
    invoice_id
):

    invoice = mongo.db.invoices.find_one({
        "_id":
            ObjectId(invoice_id)
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
            "_id":
                ObjectId(invoice_id)
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
        "_id":
            ObjectId(id)
    })

    flash(
        "Customer deleted.",
        "success"
    )

    return redirect(
        url_for("customers")
    )


@app.route(
    "/customers/edit/<id>",
    methods=["GET", "POST"]
)
def edit_customer(id):

    customer = mongo.db.customers.find_one({
        "_id": ObjectId(id)
    })

    if not customer:
        flash("Customer not found.", "danger")
        return redirect(url_for("customers"))

    if request.method == "POST":
        mongo.db.customers.update_one(
            {"_id": ObjectId(id)},
            {
                "$set": {
                    "name": request.form.get("name", "").strip(),
                    "phone": request.form.get("phone", "").strip(),
                    "email": request.form.get("email", "").strip(),
                    "address": request.form.get("address", "").strip(),
                    "gstin": request.form.get("gstin", "").strip(),
                    "updated_at": datetime.now()
                }
            }
        )

        flash("Customer updated successfully.", "success")
        return redirect(url_for("customers"))

    return render_template(
        "edit_customer.html",
        customer=customer
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
        "_id":
            ObjectId(id)
    })

    flash(
        "Product deleted.",
        "success"
    )

    return redirect(
        url_for("products")
    )


@app.route(
    "/products/edit/<id>",
    methods=["GET", "POST"]
)
def edit_product(id):

    product = mongo.db.products.find_one({
        "_id": ObjectId(id)
    })

    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("products"))

    if request.method == "POST":
        mongo.db.products.update_one(
            {"_id": ObjectId(id)},
            {
                "$set": {
                    "name": request.form.get("name", "").strip(),
                    "price": money(request.form.get("price", 0)),
                    "tax": money(request.form.get("tax", 18)),
                    "updated_at": datetime.now()
                }
            }
        )

        flash("Product updated successfully.", "success")
        return redirect(url_for("products"))

    return render_template(
        "edit_product.html",
        product=product
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
                ),

            # Optional GST fields
            "state":
                request.form.get(
                    "customer_state",
                    ""
                ),

            "state_code":
                request.form.get(
                    "customer_state_code",
                    ""
                ),

            "pincode":
                request.form.get(
                    "customer_pincode",
                    ""
                ),

            "location":
                request.form.get(
                    "customer_location",
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

        # Optional GST fields
        hsns = request.form.getlist(
            "item_hsn[]"
        )

        units = request.form.getlist(
            "item_unit[]"
        )

        items = []

        subtotal = 0.0
        tax_total = 0.0

        for i, (
            n,
            q,
            p,
            t
        ) in enumerate(
            zip(
                names,
                qtys,
                prices,
                taxes
            )
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

            hsn = (
                hsns[i]
                if i < len(hsns)
                else ""
            )

            unit = (
                units[i]
                if i < len(units)
                else "NOS"
            )

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
                    tax_amount,

                "hsn":
                    hsn.strip(),

                "unit":
                    unit.strip().upper()
                    if unit.strip()
                    else "NOS"
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
            taxable
            * tax_rate
            / 100
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
                ),

            "state":
                request.form.get(
                    "customer_state",
                    ""
                ),

            "state_code":
                request.form.get(
                    "customer_state_code",
                    ""
                ),

            "pincode":
                request.form.get(
                    "customer_pincode",
                    ""
                ),

            "location":
                request.form.get(
                    "customer_location",
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

        hsns = request.form.getlist(
            "item_hsn[]"
        )

        units = request.form.getlist(
            "item_unit[]"
        )

        items = []

        subtotal = 0.0
        tax_total = 0.0

        for i, (
            n,
            q,
            p,
            t
        ) in enumerate(
            zip(
                names,
                qtys,
                prices,
                taxes
            )
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

            hsn = (
                hsns[i]
                if i < len(hsns)
                else ""
            )

            unit = (
                units[i]
                if i < len(units)
                else "NOS"
            )

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
                    tax_amount,

                "hsn":
                    hsn.strip(),

                "unit":
                    unit.strip().upper()
                    if unit.strip()
                    else "NOS"
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
            taxable
            * tax_rate
            / 100
        )

        grand_total = money(
            taxable + final_tax
        )

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
                grand_total
                - paid_amount
            )
        )

        if (
            paid_amount >= grand_total
            and grand_total > 0
        ):

            payment_status = "Paid"

        elif paid_amount > 0:

            payment_status = (
                "Partially Paid"
            )

        else:

            payment_status = "Pending"

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

    products = list(
        mongo.db.products
        .find()
        .sort(
            "name",
            1
        )
    )

    return render_template(
        "edit_invoice.html",
        invoice=invoice,
        products=products
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
            grand_total
            - already_paid
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
        remaining
        - payment_amount
    )

    if new_remaining <= 0:

        payment_type = (
            "Final Payment"
        )

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
# PAYMENT PDF / RECEIPT
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

        return (
            "Invoice not found",
            404
        )

    payment = None

    for p in invoice.get(
        "payments",
        []
    ):

        if p.get("id") == payment_id:

            payment = p
            break

    if not payment:

        return (
            "Payment not found",
            404
        )

    buffer = io.BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    width, height = A4

    left = 20 * mm

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

    logo_drawn = draw_logo(
        c,
        left,
        height - 39 * mm,
        30 * mm,
        30 * mm
    )

    c.setFillColor(
        colors.white
    )

    c.setFont(
        "Helvetica-Bold",
        20
    )

    company_x = (
        left + 35 * mm
        if logo_drawn
        else left
    )

    c.drawString(
        company_x,
        height - 16 * mm,
        COMPANY_NAME
    )

    c.setFont(
        "Helvetica-Bold",
        8
    )

    c.drawString(
        company_x,
        height - 23 * mm,
        COMPANY_TAGLINE
    )

    c.setFont(
        "Helvetica-Bold",
        15
    )

    c.drawString(
        company_x,
        height - 34 * mm,
        "PAYMENT RECEIPT"
    )

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

    draw_logo(
        c,
        (width / 2) - 12 * mm,
        24 * mm,
        24 * mm,
        18 * mm
    )

    c.setFillColor(
        colors.black
    )

    c.setFont(
        "Helvetica-Bold",
        9
    )

    c.drawCentredString(
        width / 2,
        20 * mm,
        COMPANY_NAME
    )

    c.setFont(
        "Helvetica-Oblique",
        8
    )

    c.drawCentredString(
        width / 2,
        14 * mm,
        COMPANY_TAGLINE
    )

    c.setFont(
        "Helvetica",
        8
    )

    c.drawCentredString(
        width / 2,
        8 * mm,
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
# DELETE INVOICE
# =========================================================

@app.route(
    "/invoice/delete/<invoice_id>"
)
def delete_invoice(invoice_id):

    mongo.db.invoices.delete_one({
        "_id":
            ObjectId(invoice_id)
    })

    flash(
        "Invoice deleted.",
        "success"
    )

    return redirect(
        url_for("invoices")
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

        return (
            "Invoice not found",
            404
        )

    buffer = io.BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    width, height = A4

    left = 20 * mm

    y = height - 22 * mm

    # HEADER

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

    logo_drawn = draw_logo(
        c,
        left,
        height - 39 * mm,
        30 * mm,
        30 * mm
    )

    c.setFillColor(
        colors.white
    )

    c.setFont(
        "Helvetica-Bold",
        22
    )

    company_x = (
        left + 35 * mm
        if logo_drawn
        else left
    )

    c.drawString(
        company_x,
        height - 16 * mm,
        COMPANY_NAME
    )

    c.setFont(
        "Helvetica-Bold",
        8
    )

    c.drawString(
        company_x,
        height - 23 * mm,
        COMPANY_TAGLINE
    )

    c.setFont(
        "Helvetica-Bold",
        15
    )

    c.drawString(
        company_x,
        height - 34 * mm,
        "INVOICE"
    )

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

    c.drawRightString(
        width - left,
        height - 23 * mm,
        inv.get(
            "date",
            ""
        )
    )

    y = height - 58 * mm

    # BILL TO

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

    # ITEMS TABLE

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

    # TOTALS

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

    # PAYMENT SUMMARY

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

    # PAYMENT HISTORY

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

    # NOTES

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

    # FOOTER LOGO

    draw_logo(
        c,
        (width / 2) - 12 * mm,
        18 * mm,
        24 * mm,
        18 * mm
    )

    # FOOTER

    c.setFillColor(
        colors.black
    )

    c.setFont(
        "Helvetica-Bold",
        9
    )

    c.drawCentredString(
        width / 2,
        14 * mm,
        COMPANY_NAME
    )

    c.setFont(
        "Helvetica-Oblique",
        8
    )

    c.drawCentredString(
        width / 2,
        9 * mm,
        COMPANY_TAGLINE
    )

    c.setFont(
        "Helvetica",
        8
    )

    c.drawCentredString(
        width / 2,
        4 * mm,
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
# MAIN
# =========================================================

if __name__ == "__main__":

    print(
        "Logo path:",
        LOGO_PATH
    )

    print(
        "Logo exists:",
        os.path.exists(
            LOGO_PATH
        )
    )

    print(
        "Seller GSTIN:",
        SELLER_GSTIN
    )

    print(
        "Seller State Code:",
        SELLER_STATE_CODE
    )

    app.run(
        debug=True
    )