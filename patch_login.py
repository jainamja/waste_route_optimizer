import io
import re

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("@app.route('/api/deploy_template/<int:t_id>', methods=['POST'])\n@login_required", "@app.route('/api/deploy_template/<int:t_id>', methods=['POST'])")

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
