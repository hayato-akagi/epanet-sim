def parse_inp_geometry(inp_path):
    """INPファイルからノードとリンクの幾何情報を抽出"""
    nodes = {}  # id -> {x, y, z}
    links = []  # (source, target)
    
    current_section = None
    
    try:
        with open(inp_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('['):
                    current_section = line
                    continue
                if line.startswith(';') or not line:
                    continue
                
                parts = line.split()
                
                if current_section == "[COORDINATES]":
                    if len(parts) >= 3:
                        nid, x, y = parts[0], float(parts[1]), float(parts[2])
                        if nid not in nodes:
                            nodes[nid] = {'z': 0}
                        nodes[nid]['x'] = x
                        nodes[nid]['y'] = y
                
                elif current_section in ["[JUNCTIONS]", "[RESERVOIRS]", "[TANKS]"]:
                    if len(parts) >= 2:
                        nid = parts[0]
                        elev = float(parts[1])
                        if nid not in nodes:
                            nodes[nid] = {}
                        nodes[nid]['z'] = elev
                        
                elif current_section == "[PIPES]":
                    if len(parts) >= 3:
                        links.append((parts[1], parts[2]))
                        
        return nodes, links
    except Exception as e:
        return {}, []

def parse_inp_details(inp_path):
    """INPファイルからノードタイプとリンク詳細を抽出"""
    node_types = {}  # node_id -> type
    link_dict = {}   # link_id -> (node1, node2)
    
    current_section = None
    
    try:
        with open(inp_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('['):
                    current_section = line
                    continue
                if line.startswith(';') or not line:
                    continue
                
                parts = line.split()
                
                if current_section == "[JUNCTIONS]" and len(parts) >= 2:
                    node_types[parts[0]] = 'Junction'
                elif current_section == "[RESERVOIRS]" and len(parts) >= 2:
                    node_types[parts[0]] = 'Reservoir'
                elif current_section == "[TANKS]" and len(parts) >= 2:
                    node_types[parts[0]] = 'Tank'
                elif current_section == "[PIPES]" and len(parts) >= 3:
                    link_dict[parts[0]] = (parts[1], parts[2])
                elif current_section == "[VALVES]" and len(parts) >= 3:
                    link_dict[parts[0]] = (parts[1], parts[2])
    except Exception as e:
        pass
    
    return node_types, link_dict