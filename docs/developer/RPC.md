# RPC Communication

## Overview
RPC or Remote Procedure Call is a communication pattern between a client and a server where the client can access an 
object provided by the server as if it was a local object. In a sense, the client serves as a proxy of an object and 
the server makes the actual object available.

In Plant-Imager3 this communication protocol is implemented in the module `plantimager.commons.RPC` with the main two 
classes `RPCClient` and `RPCServer` as well as other auxiliary classes `RPCSignal`, `RPCProperty` and `RPCSignalReceiver`.

 - `RPCServer`: When used as a parent to a class, makes that class available as an RPC object
 - `RPCClient`: Proxy of an RPC object which connects to the `RPCServer` providing said object
 - `RPCSignal`: Declare signals for RPC objects which when emitted server-side are also emitted client-side, calling any connected method
 - `RPCProperty`: Declare python-style properties that are made available to the client
 - `RPCSignalReceiver`: Internal signal receiver client-side in charge of receiving and copying signals from the server


## Communication diagram

### Class diagram

Class diagram for a typical implementation where we want to make available te class `AbstractDevice`. To that end we
implement `DeviceServer` which inherits from both `AbstractDevice` and `RPCServer` and in which we implement the various
methods defined in the abstract class; `DeviceServer` will serve the implementation.

Client-side we simply declare a class `DeviceClient`inheriting from both `AbstractDevice` and `RPCClient` and which must
be decorated with the classmethod `RPCClient.register_interface()`. Implementation of the abstract methods of `AbstractDevice`
is automatically handled, creating proxy methods which will call the proper methods from `DeviceServer`.

```mermaid
---
title: Animal example
---
classDiagram
    note for AbstractDevice "Abstract class defining the interface which will be exposed via RPC"
    RPCServer <|-- DeviceServer
    AbstractDevice <|-- DeviceServer
    AbstractDevice <|-- DeviceClient
    RPCClient <|-- DeviceClient
    RPCClient *-- RPCSignalReceiver
    class RPCServer {
        +zmq.Context context
        +String url
        +int port
        +String name
        +String registry_addr
        +String peer_addr
        -zmq.Socket _socket
        
        +register_to_registry(type_name, name, registry_url)
        +register_method_json(timeout)$
        +register_method_buffer(timeout)$
        +stop_server()
        +serve_forever()
        -_send_signal(signal_name, *args)
        -_exec_json(method, params)
        -_exec_buffer(method, params)
        -_finalize()
    }
    
    class RPCClient {
        +zmq.Context context
        +String url
        +zmq.Socket socket
        +String own_address
        +String peer_address
        +String name
        
        +execute(method_name, params)
        +stop_server()
        +register_interface(interface)$
        -_finalizer()
        -_method_proxy(func, self, *args, **kwargs)$
        -_property_getter_proxy(property_name)
        -_property_setter_proxy(value, property_name)
    }
    class RPCSignalReceiver {
        +zmq.Context context
        +String url
        +dict[str, RPCSignals] signals
        +zmq.Socket socket
        +int port
        +run()
        +stop()
    }
    class AbstractDevice{
        <<Abstract>>
        +RPCSignal some_signal$
        +RPCProperty some_property*
        +some_method()*
    }
    class DeviceServer{
    }
    class DeviceClient{
    }

```

### Connection diagram

```mermaid
sequenceDiagram
    participant signal_recv as RPCSignalReceiver
    participant client as Device Client
    participant server as Device Server
    activate client
    Note over server: The method serve_forever() must have been called
    Note over client: in __init__ after <br/> the socket is connected
    client->>+server: FIND_PEER_ADDRESS
    Note right of server: Creates a socket server
    server->>client: url
    client<<-->>server: connects to temp server
    deactivate server
    
    
    Note over client,server: Getting peer address and <br/> closing connection and temporary server
    client->>+server: GET_INVENTORY
    server->>-client: methods, properties and signals inventory

    opt RPCSignals declared
    Note over signal_recv, client: Start Signal Receiver thread
    client->>+signal_recv: __init__()
    signal_recv-->>-client: 
    client->>+server: INIT_SIGNALS_HANDLING
    Note right of server: Connect to signal socket and <br/> connect signals to _send_signal()
    server->>-client: success

    end

    deactivate client

```


### Method call

```mermaid

sequenceDiagram
    participant other
    participant client as Device Client
    participant server as Device Server

    Note over client, server: server.serve_forever() called <br/> and client connected
    other->>+client: some_method()
    Note over client: some_method is a proxy method
    client->>+client: execute()

    Alt is json_method
        client->>+server: METHOD_CALL
        server->>+server: _exec_json()
        server->>server: some_method()
        deactivate server
        server->>-client: result
    else is buffer_method
        client->>+server: METHOD_CALL
        server->>+server: _exec_buffer()
        server->>server: some_method()
        deactivate server
        server->>-client: result
    end
    deactivate client

    client-->>-other: result
```

### Emitting a signal
```mermaid
sequenceDiagram
    participant client_signal as Signal proxy
    participant recv as RPCSignalReceiver
    participant server as Device Server
    participant server_signal as Original Signal

    Note over recv, server: server.serve_forever() called <br/> and client connected

    Note over server_signal: emit() called
    activate server_signal
    server_signal->>+server: _send_signal()
    server->>+recv: EMIT_SIGNAL
    Note over recv: select corresponding signal
    alt is blocking
        recv->>+client_signal: emit()
        client_signal-->>-recv: 
        recv->>server: success
    else
        recv->>server: success
        recv->>+client_signal: emit()
        client_signal-->>-recv: 
        deactivate recv
    end
    

    server-->>-server_signal: 
    deactivate server_signal
```

### Property getter
```mermaid
sequenceDiagram
    participant other
    participant client as Device Client
    participant server as Device Server

    Note over client, server: server.serve_forever() called <br/> and client connected
    other->>+client: some_property getter()
    Note over client: some_property getter is a proxy method <br/> RPCClient._property_getter_proxy() is called

    client->>+server: PROPERTY_GET
    server->>server: some_property getter()
    server->>-client: result

    client-->>-other: result

```

### Property setter
```mermaid
sequenceDiagram
    participant other
    participant client as Device Client
    participant server as Device Server

    Note over client, server: server.serve_forever() called <br/> and client connected
    other->>+client: some_property setter()
    Note over client: some_property setter is a proxy method <br/> RPCClient._property_setter_proxy() is called

    client->>+server: PROPERTY_SET
    server->>server: some_property setter()
    server->>-client: result

    client-->>-other: result

```

