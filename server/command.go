package command

import (
	"encoding/binary"
	"fmt"
	"io"

	"goprotobuf.googlecode.com/hg/proto"
)

func ReceiveRequest(reader io.Reader) (*Request, error) {
	req := new(Request)
	if err := receiveProtoBuf(reader, req); err != nil {
		return nil, err
	}
	return req, nil
}

func ReceiveResponse(reader io.Reader) (*Response, error) {
	res := new(Response)
	if err := receiveProtoBuf(reader, res); err != nil {
		return nil, err
	}
	return res, nil
}

func receiveProtoBuf(reader io.Reader, pb interface{}) error {
	fmt.Println("ReceiveRequest...")
	var size uint64;
	if err := binary.Read(reader, binary.LittleEndian, &size); err != nil {
		return err
	}		
	fmt.Println("size =", size)
	buf := make([]byte, size)
	if _, err := io.ReadFull(reader, buf); err != nil {
		return err
	}
	return proto.Unmarshal(buf, pb)
}

func SendRequest(writer io.Writer, req *Request) error {
	return sendProtobuf(writer, req)
}

func SendResponse(writer io.Writer, res *Response) error {
	return sendProtobuf(writer, res)
}

func sendProtobuf(writer io.Writer, pb interface{}) error {
	var data []byte
	var err error
	if data, err = proto.Marshal(pb); err != nil {
		return err
	}
	size := uint64(len(data))
	binary.Write(writer, binary.LittleEndian, size)
	_, err = writer.Write(data)
	return err
}
