# Note: These need to match the version used in namely/protoc-all when a tag is changed.
ARG alpine=3.8
ARG go=1.10.3
ARG grpc

FROM golang:$go-alpine$alpine AS builder

#Protoc Gen Validate isn't apart of namely/protoc-all image.
RUN set -ex && apk --update --no-cache add \
    git

RUN git clone https://github.com/lyft/flyteproto.git /flyteproto

# Reuse the namely/protoc-all container to get the rest of the protoc dependencies.
FROM namely/protoc-all:1.14_0 as final
RUN set -ex && apk --update add \
    python3

RUN pip3 install protobuf
COPY --from=builder /go/bin/protoc-gen-validate /usr/local/bin/protoc-gen-validate
COPY --from=builder /go/src/github.com/lyft/protoc-gen-validate /usr/local/include/
COPY --from=builder /flyteproto/ /usr/local/include/

COPY ./entrypoint.py /usr/local/bin
COPY ./protodoc.py /usr/local/bin


WORKDIR /defs
ENTRYPOINT [ "python3" , "/usr/local/bin/generate_protos.py"]

