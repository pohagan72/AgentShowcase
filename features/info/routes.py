# from flask import render_template # Not needed if only serving static content via /content/ route

def define_info_routes(app):
    # This feature is currently just static content loaded via the
    # /content/info route handled in the main app.py.
    # If you had specific backend logic or forms for the info page,
    # you would add @app.route decorators here.
    pass # No specific routes needed for now beyond what main app handles for content loading