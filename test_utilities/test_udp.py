import socket

def run_udp_broadcast_client(port):
    # Crée un socket UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Lie le socket à toutes les adresses disponibles sur le port spécifié
    sock.bind(('', port))

    print(f"Client UDP en écoute sur le port {port}...")

    try:
        while True:
            # Reçoit les données et l'adresse de l'expéditeur
            data, addr = sock.recvfrom(1024)  # Buffer size is 1024 bytes
            print(f"Message reçu de {addr}: {data.decode()}")
    except KeyboardInterrupt:
        print("Arrêt du client.")
    finally:
        sock.close()

if __name__ == "__main__":
    # Paramètres du client
    PORT = 4553

    run_udp_broadcast_client(PORT)
