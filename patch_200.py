import io

with io.open('waste_route_optimizer.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("return jsonify({'error': f'Database error during deploy: {str(e)}'}), 500", "return jsonify({'error': f'Database error during deploy: {str(e)}'}), 200")

with io.open('waste_route_optimizer.py', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
