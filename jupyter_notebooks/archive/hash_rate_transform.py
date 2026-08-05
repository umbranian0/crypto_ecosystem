import json
import csv
import os
from datetime import datetime

# Ensure the data folder exists
os.makedirs('data', exist_ok=True)

# Input and output file paths
input_file = 'data/n-unique-addresses.json'
output_file = os.path.join('data', 'n-unique-addresses.csv')

# Load JSON data
with open(input_file, 'r') as f:
    data = json.load(f)

# Extract the metric name for the data series
metric_name = data['metric1']
data_points = data[metric_name]

# Write to CSV file
with open(output_file, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['timestamp', 'date', metric_name])  # CSV header

    for point in data_points:
        timestamp = point['x']
        value = point['y']
        date = datetime.utcfromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        writer.writerow([timestamp, date, value])

print(f'Data successfully written to {output_file}')
