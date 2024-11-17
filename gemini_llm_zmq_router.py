import zmq
import time

def main():
    context = zmq.Context()
    frontend = context.socket(zmq.XPUB)
    backend = context.socket(zmq.XSUB)

    frontend.bind("tcp://*:5559")
    backend.bind("tcp://*:5560")

    zmq.proxy(frontend, backend)

if __name__ == "__main__":
    main()