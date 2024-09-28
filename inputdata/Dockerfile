FROM spack/ubuntu-jammy:0.22.2

ARG DATA_FILE="files.txt"

ENV DATA_FILE=${DATA_FILE}

RUN apt-get update
RUN apt-get -y upgrade
RUN apt-get -y remove cmake
RUN apt-get -y install software-properties-common
RUN add-apt-repository universe
RUN apt-get update && apt-get -y install wget

RUN python -m pip install netcdf4 pyyaml psutil pylint nanobind

RUN apt-get -y autoremove

ENV INPUT_DATA_DIR=/projects/e3sm/inputdata
RUN mkdir -p $INPUT_DATA_DIR

ENV USER=ghciocitester

RUN git config --global user.email "${USER}@${USER}.${USER}"
RUN git config --global user.name "${USER}"

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=America/Los_Angeles

ENV LANGUAGE=en_US:en \
    LANG=en_US.UTF-8

RUN mkdir -p /app/ \
&& (echo "" \
&&  echo "cat /app/files.txt | while read -r line; do" \
&&  echo "    file_url=\$line" \
&&  echo "    file_loc=\${line//https\:\/\/web\.lcrc\.anl\.gov\/public\/e3sm\/inputdata/${INPUT_DATA_DIR}}" \
&&  echo "    mkdir -p \$( dirname -- \"\$file_loc\")" \
&&  echo "    touch \"\$file_loc\"" \
&&  echo "    echo \"downloading from \$file_url\"" \
&&  echo "    echo \"downloading to \$file_loc\"" \
&&  echo "    wget -q -O \"\$file_loc\" \"\$file_url\"" \
&&  echo "done" \
&&  echo "") > /app/download.sh

RUN chmod +x /app/download.sh

COPY ${DATA_FILE} /app/files.txt
RUN /app/download.sh

ENTRYPOINT ["/bin/bash", "--rcfile", "/etc/profile", "-l"]
