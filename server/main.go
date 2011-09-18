package main

import (
	"fmt"
	"http"
	"io"
	"json"
	"log"
	"time"
	"websocket"
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

func HandleWebSocket(ws *websocket.Conn) {
	fmt.Println("Start HandleWebSocket.")
	ch := CreateReadChannel(ws)
	interval := time.Tick(1e9)
  for count := 0;; count++ {
		closed := false
	  select  {
		case message, ok := <- ch:
			if ok {
				fmt.Println("Recived", message, "from the browser.")
			} else {
				fmt.Println("The web socket connection was closed by peer.")
				closed = true
			}
		case _ = <- interval:
		  message := make(map[string]interface{})
			if count % 3 != 2 {
				message["cmd"] = "show"
				message["url"] = "/test.html"
			} else {
				message["cmd"] = "close"
				message["url"] = "/test.html"
			}
			message_json, _ := json.Marshal(message)
			fmt.Println("Writing", string(message_json))
			io.WriteString(ws, string(message_json))
			fmt.Println("Done")
		}
		if closed {
			break
		}
	}
}

func NotFoundServer(w http.ResponseWriter, req *http.Request) {
	fmt.Println("Not found")
	w.WriteHeader(404)
	io.WriteString(w, "Not found\n")
}

func main() {
	fmt.Println("main")
	http.HandleFunc("/", NotFoundServer)
	http.Handle("/ws", websocket.Handler(HandleWebSocket))
	err := http.ListenAndServe(":8888", nil)
	if err != nil {
		log.Fatal("Failed to listen:", err.String())
	}
}
