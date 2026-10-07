"""GST e-Invoice JSON integration helper.

The existing invoice application keeps its GST calculation and JSON generation
logic in app.py. This module provides a small reusable entry point without
changing that existing logic.
"""

def generate_gst_einvoice_json(invoice):
    """Generate GST e-Invoice JSON using the application's existing generator."""
    from app import generate_gst_einvoice_json as _generate
    return _generate(invoice)
