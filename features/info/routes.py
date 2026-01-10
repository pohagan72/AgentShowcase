# features/info/routes.py
from flask import Blueprint

bp = Blueprint('info', __name__)

# This feature serves static content via main_routes, 
# but we keep the blueprint structure for consistency.