FROM alpine:3.15

# Install Python and all build dependencies
RUN apk update\
    && apk add python3~=3.9\
            wget~=1.21\
            py3-pip~=20.3\
            python3-dev~=3.9\
            openssl-dev~=1.1\
            rust~=1.56\
            cargo~=1.56\
            build-base~=0.5\
            libffi-dev~=3.4.2\
            postgresql13-client~=13.7\
    && pip install wheel~=0.37\
        paramiko~=2.11\
        mediawiki-dump~=1.0.0\
        gql~=3.4\
        psycopg~=3.0\
        ldap3~=2.9\
        wikijspy\
        wikijspy-ext\
    && wget https://github.com/jgm/pandoc/releases/download/2.18/pandoc-2.18-linux-amd64.tar.gz\
    && tar -xf /pandoc-2.18-linux-amd64.tar.gz pandoc-2.18/bin/pandoc && mv /pandoc-2.18/bin/pandoc /usr/bin\
    && apk del wget\
            python3-dev\
            openssl-dev\
            rust\
            cargo\
            build-base\
            libffi-dev\
    && rm -r /pandoc-2.18 /pandoc-2.18-linux-amd64.tar.gz /root/.cargo /root/.cache

COPY ./mediawiki2wikijs.py /mediawiki2wikijs.py

RUN chmod 755 /mediawiki2wikijs.py

RUN mkdir /data

CMD [ "/mediawiki2wikijs.py" ]
