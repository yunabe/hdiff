include $(GOROOT)/src/Make.inc

all: main command_pb2.py

main: main.$(O)
	$(LD) -o main main.$(O)

main.$(O): main.go command.$(O)
	$(GC) main.go

command.pb.go: command.proto
	protoc --go_out=. command.proto

command_pb2.py: command.proto
	protoc --python_out=. command.proto

command.$(O): command.go command.pb.go
	$(GC) -o command.$(O) command.go command.pb.go

clean:
	rm -f *_pb2.py *.pb.go *.$(O) main
