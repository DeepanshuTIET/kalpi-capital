"""
Utility functions for getting client information for Angel API headers.
"""
import socket
import uuid


def get_client_info():
    """
    Get client IP and MAC address information for Angel API headers.
    
    Returns:
        tuple: (client_local_ip, client_public_ip, mac_address)
    """
    # Get local IP address
    try:
        client_local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        client_local_ip = '127.0.0.1'
    
    # For now, use local IP as public IP (in production, you might want to get actual public IP)
    client_public_ip = client_local_ip
    
    # Get MAC address
    try:
        mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                               for elements in range(0, 2*6, 2)][::-1])
    except Exception:
        mac_address = '00:00:00:00:00:00'
    
    return client_local_ip, client_public_ip, mac_address


def get_angel_headers(auth_token, api_key):
    """
    Get standardized headers for Angel API requests.
    
    Args:
        auth_token: JWT authentication token
        api_key: Angel API key
        
    Returns:
        dict: Complete headers dictionary for Angel API
    """
    client_local_ip, client_public_ip, mac_address = get_client_info()
    
    return {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-UserType': 'USER',
        'X-SourceID': 'WEB',
        'X-ClientLocalIP': client_local_ip,
        'X-ClientPublicIP': client_public_ip,
        'X-MACAddress': mac_address,
        'X-PrivateKey': api_key
    }
