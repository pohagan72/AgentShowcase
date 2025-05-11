from flask import request
import time

def define_summarization_routes(app):

    @app.route('/process/summarize', methods=['POST'])
    def process_summarize_action():
        text = request.form.get('text_to_summarize', '')
        # time.sleep(1)

        if text:
            # TODO: Implement actual summarization logic
            summary = text[:150] + "..." if len(text) > 150 else text # Simple truncation for demo
            return f"<p><strong>Summary (Demo):</strong> {summary}</p>"
        return "<p class='error-message'>No text submitted for summarization.</p>"