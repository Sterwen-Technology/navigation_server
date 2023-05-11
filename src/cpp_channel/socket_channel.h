//
// Created by laurent on 02/03/23.
//

#ifndef NAVIGATION_SERVER_SOCKET_CHANNEL_H
#define NAVIGATION_SERVER_SOCKET_CHANNEL_H

#include <sys/socket.h>
#include <netinet/in.h>

class TCP_Channel {
protected:
    int sock_fd;
    char* address;
    int port;
    struct sockaddr_in serv_addr;
    char* buffer;
    int buffer_len;

public:
    TCP_Channel();

    int open();
    int close();

};
#endif //NAVIGATION_SERVER_SOCKET_CHANNEL_H
