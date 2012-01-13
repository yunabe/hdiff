package main

import (
	"bufio"
	"regexp"
	"fmt"
	"net/http"
	"io"
	"encoding/json"
	"log"
	"net"
	"math/rand"
	"strconv"
	"time"
	"net/url"
	"net/http/httputil"
	"websocket"

	"./command"
	"goprotobuf.googlecode.com/hg/proto"
)

func ReadWebSocket(ws *websocket.Conn, ch chan string) {
	msg := make([]byte, 100 * 1000)
	defer close(ch)
	for {
		n, err := ws.Read(msg)
		if err != nil || n == 0 {
			break
		} else {
			ch <- string(msg[:n])
		}
	}
}

func CreateReadChannel(ws *websocket.Conn) chan string {
	ch := make(chan string)
	go ReadWebSocket(ws, ch)
	return ch
}

var commandChannel chan interface{}

func HandleWebSocket(ws *websocket.Conn) {
	fmt.Println("Start HandleWebSocket.")
	ch := CreateReadChannel(ws)
  for count := 0;; count++ {
		closed := false
	  select  {
		case message, ok := <- ch:
			if ok {
				fmt.Println("Received", message, "from the browser.")
			} else {
				fmt.Println("The web socket connection was closed by peer.")
				closed = true
			}
		case command := <- commandChannel:
			command_json, err := json.Marshal(command)
			if err != nil {
				fmt.Println("Failed to convert a command to json:", command)
				continue
			}
			fmt.Println("Writing", string(command_json))
			io.WriteString(ws, string(command_json))
			fmt.Println("Done")
		}
		if closed {
			break
		}
	}
}

func NotFoundServer(w http.ResponseWriter, req *http.Request) {
	fmt.Println("Not found:", req.URL.String())
	w.WriteHeader(404)
	io.WriteString(w, "Not found\n")
}

var commandManager CommandManager

func main() {
	commandChannel = make(chan interface{})

	go listenAndServeCommand()
	rand.Seed(int64(time.Now().Nanosecond()))
	http.HandleFunc("/", NotFoundServer)
	http.Handle("/ws", websocket.Handler(HandleWebSocket))
	commandManager.root = "/cmd"
	commandManager.dict = make(map[uint32]Command)
	http.Handle(commandManager.root + "/", &commandManager)
	err := http.ListenAndServe(":8888", nil)
	if err != nil {
		log.Fatal("Failed to listen:", err)
	}
}

type Command interface {
	Id() uint32
	ServeHTTP(w http.ResponseWriter, r *http.Request)
	Dispose()
}

type CommandManager struct {
	root string
	dict map[uint32]Command
}

func (manager *CommandManager) Register(cmd Command) {
	fmt.Println("Registering id: id =", cmd.Id())
	manager.dict[cmd.Id()] = cmd
}

func (manager *CommandManager) Unregister(cmd Command) {
	fmt.Println("Unregister cmd: id =", cmd.Id())
	delete(manager.dict, cmd.Id())
}

func (manager *CommandManager) ServeHTTP(w http.ResponseWriter,
                                         r *http.Request) {
	fmt.Println("r.URL =", r.URL)
	pattern, _ := regexp.Compile("^" + manager.root + "/(\\d+)(/.*)$")
	var matches []string = pattern.FindStringSubmatch(r.URL.String())
	if len(matches) != 3 {
		fmt.Println("The wrong pattern:", r.URL.String())
		return
	}
	id, err := strconv.ParseUint(matches[1], 10, 64)
	if err != nil {
		fmt.Println("Failed to parse ID:", matches[1])
		return
	}
	cmd, ok := manager.dict[uint32(id)]
	if !ok {
		fmt.Println("Invalid Id:", id)
		return
	}
	r.URL, _ = url.Parse(matches[2])
	cmd.ServeHTTP(w, r)
}

func listenAndServeCommand() {
	laddr := net.UnixAddr{Net: "unix", Name: "/tmp/sock"}
	listener, err := net.ListenUnix("unix", &laddr)
	if err != nil {
		panic(err)
	}
	defer listener.Close()
	for {
		c, _ := listener.AcceptUnix()
		go handleCommandRequst(c)
	}
}

func handleCommandRequst(conn *net.UnixConn) {
	defer conn.Close()
	r := bufio.NewReader(conn)

	var cmds []Command
	for {
		req, err := command.ReceiveRequest(r)
		if err != nil {
			fmt.Println("Failed to receive a request:", err)
			break
		}
		var mode command.Request_Mode
		if req.Mode == nil {
			mode = command.Default_Request_Mode
		} else {
			mode = *req.Mode
		}
		switch mode {
		case command.Request_PROXY:
			fmt.Println("Proxy!")
			fmt.Printf("proxy_addr: %s\n", *req.ProxyAddr)
			cmd := createProxyCommand(req)
			cmd.Register()
			cmds = append(cmds, cmd)
		default:
			cmd := createShowPageCommand(rand.Uint32(), req)
			cmd.Register()
			cmds = append(cmds, cmd)
		}
	}
	for _, cmd := range cmds {
		cmd.Dispose()
	}
}

type FileHandler struct {
	file *command.Request_File
}

func (handler *FileHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	header := w.Header()
	header.Set("Content-Length", strconv.Itoa(len(handler.file.Data)))
	header.Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	w.Write(handler.file.Data)	
}

func createFileHandler(file *command.Request_File) *FileHandler {
	handler := new(FileHandler)
	handler.file = file
	return handler
}

func createProxyCommand(req *command.Request) *proxyCommand {
	proxy := NewResverseProxy(*req.ProxyAddr)
	return &proxyCommand{id: rand.Uint32(), proxy: proxy}
}

type proxyCommand struct {
	id uint32
	proxy *httputil.ReverseProxy
}

func (cmd *proxyCommand) Id() uint32 {
	return cmd.id
}

func (cmd *proxyCommand) Register() {
	commandManager.Register(cmd)

	message := make(map[string]interface{})
	message["cmd"] = "show"
	message["url"] = fmt.Sprintf("/cmd/%d/index.html", cmd.id)
	commandChannel <- message
}

func (cmd *proxyCommand) Dispose() {
	commandManager.Unregister(cmd)

	message := make(map[string]interface{})
	message["cmd"] = "close"
	message["url"] = fmt.Sprintf("/cmd/%d/", cmd.id)
	commandChannel <- message
}

func NewResverseProxy(proxyAddr string) *httputil.ReverseProxy {
	target := url.URL{
	    Scheme: "http",
	    Host: proxyAddr,
	}
	return httputil.NewSingleHostReverseProxy(&target)
}



func (cmd *proxyCommand) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	cmd.proxy.ServeHTTP(w, r)
}

type showPageCommand struct {
	id uint32
	mux *http.ServeMux
	req *command.Request
}

func (cmd *showPageCommand) Id() uint32 {
	return cmd.id
}

func (cmd *showPageCommand) Register() {
	commandManager.Register(cmd)

	for _, page := range cmd.req.Page {
		message := make(map[string]interface{})
		message["cmd"] = "show"
		message["url"] =
			fmt.Sprintf("/cmd/%d/%s", cmd.id, proto.GetString(page.Name))
		commandChannel <- message
	}
}

func (cmd *showPageCommand) Dispose() {
	commandManager.Unregister(cmd)

	message := make(map[string]interface{})
	message["cmd"] = "close"
	message["url"] = fmt.Sprintf("/cmd/%d/", cmd.id)
	commandChannel <- message
}

func (cmd *showPageCommand) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	cmd.mux.ServeHTTP(w, r)
}

func createShowPageCommand(id uint32, req *command.Request) *showPageCommand {
	cmd := new(showPageCommand)
	cmd.id = id
	cmd.req = req
	cmd.mux = http.NewServeMux()
	for _, page := range req.Page {
		path := fmt.Sprintf("/" + *page.Name)
		cmd.mux.Handle(path, createFileHandler(page))
	}
	for _, page := range req.AdditionalFile {
		path := fmt.Sprintf("/" + *page.Name)
		cmd.mux.Handle(path, createFileHandler(page))
	}
	return cmd
}
