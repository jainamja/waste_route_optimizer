from waste_route_optimizer import read_data_file
c = read_data_file('uploads/Bintix GGPL - Tuesday Dry Waste collection.docx')
for x in c:
    print(f"{x['id']}: {x['lat']}, {x['lng']}")
