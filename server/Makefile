include $(GOROOT)/src/Make.inc

main: main.$(O)
	$(LD) -o main main.$(O)

main.$(O): main.go
	$(GC) main.go

clean:
	rm -f *.$(O) main
