FROM spack/ubuntu-jammy:0.22.2

LABEL org.opencontainers.image.description="E3SM ghci container is mainly for testing on github actions"

ARG GCC_VERSION=11.4.0
ARG MPICH_VERSION=3.4.3
ARG SZIP_VERSION=2.1.1
ARG HDF5_VERSION=1.12.3
ARG NETCDFC_VERSION=4.9.2
ARG NETCDFCXX_VERSION=4.2
ARG NETCDFFORTRAN_VERSION=4.6.1
ARG PNETCDF_VERSION=1.12.1

ENV GCC_VERSION=${GCC_VERSION}
ENV MPICH_VERSION=${MPICH_VERSION}
ENV SZIP_VERSION=${SZIP_VERSION}
ENV HDF5_VERSION=${HDF5_VERSION}
ENV NETCDFC_VERSION=${NETCDFC_VERSION}
ENV NETCDFCXX_VERSION=${NETCDFCXX_VERSION}
ENV NETCDFFORTRAN_VERSION=${NETCDFFORTRAN_VERSION}
ENV PNETCDF_VERSION=${PNETCDF_VERSION}

RUN apt-get update
RUN apt-get -y upgrade
RUN apt-get -y remove cmake
RUN apt-get -y install software-properties-common
RUN add-apt-repository universe
RUN apt-get update && apt-get -y install \
    locales csh m4 libcurl4-openssl-dev \
    libz-dev gcc g++ gfortran liblapack-dev make git \
    git wget subversion libxml2-dev libxml2-utils libxml-libxml-perl \
    libswitch-perl build-essential checkinstall zlib1g-dev libssl-dev python3-distutils

# TODO: move to env file (spack.yaml)?
RUN mkdir -p /opt/spack-environment \
&&  (echo "spack:" \
&&   echo " " \
&&   echo "  definitions:" \
&&   echo "    - compilers: [gcc@${GCC_VERSION}]" \
&&   echo "    - mpis: [mpich@${MPICH_VERSION}]" \
&&   echo "    - mpipkgs:"  \
&&   echo "      - hdf5@${HDF5_VERSION}" \
&&   echo "      - netcdf-c@${NETCDFC_VERSION}" \
&&   echo "      - netcdf-cxx@${NETCDFCXX_VERSION}" \
&&   echo "      - netcdf-fortran@${NETCDFFORTRAN_VERSION}" \
&&   echo "      - parallel-netcdf@${PNETCDF_VERSION}" \
&&   echo "    - othpkgs:" \
&&   echo "      - cmake" \
&&   echo "      - cprnc" \
&&   echo "      - yaml-cpp" \
&&   echo "      - fmt" \
&&   echo "      - spdlog" \
&&   echo " " \
&&   echo "  specs:" \
&&   echo "    - szip" \
&&   echo "    - matrix:" \
&&   echo "      - [\$mpis]" \
&&   echo "      - [\$%compilers]" \
&&   echo "    - matrix:" \
&&   echo "      - [\$othpkgs]" \
&&   echo "      - [\$%compilers]" \
&&   echo "    - matrix:" \
&&   echo "      - [\$mpipkgs]" \
&&   echo "      - [\$^mpis]" \
&&   echo "      - [\$%compilers]" \
&&   echo " " \
&&   echo "  concretizer:" \
&&   echo "    unify: true" \
&&   echo " " \
&&   echo "  config:" \
&&   echo "    install_tree: /opt/software" \
&&   echo " " \
&&   echo "  view: /usr/local/packages" \
&&   echo "") > /opt/spack-environment/spack.yaml

# TODO: do these intervene with each other?
# https://cache.spack.io/tag/v0.22.2/
RUN spack mirror add v0.22.2 https://binaries.spack.io/v0.22.2
RUN spack buildcache keys --install --trust
# https://cache.spack.io/tag/v0.22.1/?stack=e4s
RUN spack mirror add v0.22.2-e4s https://binaries.spack.io/v0.22.2/e4s
RUN spack buildcache keys --install --trust
# https://cache.spack.io/tag/v0.22.2/?stack=root#
RUN spack mirror add v0.22.2-root https://binaries.spack.io/v0.22.2/root
RUN spack buildcache keys --install --trust

# TODO: add e4s inventory when they support ubuntu 22.04+
# # https://oaciss.uoregon.edu/e4s/inventory.html
# RUN spack mirror add E4S-24.0 https://cache.e4s.io/24.0
# RUN spack buildcache keys -it
# RUN spack mirror add E4S https://cache.e4s.io
# RUN spack buildcache keys -it

RUN cd /opt/spack-environment && spack env activate . && spack install --fail-fast && spack gc -y

RUN cd /opt/spack-environment && \
    spack env activate --sh -d . >> /etc/profile.d/z10_spack_environment.sh

ENV INPUT_DATA_DIR=/projects/e3sm/inputdata
RUN mkdir -p $INPUT_DATA_DIR

RUN mkdir -p /projects/e3sm/inputdata/atm/cam/physprops/
RUN wget https://web.lcrc.anl.gov/public/e3sm/inputdata/atm/cam/physprops/p3_lookup_table_1.dat-v4.1.2
RUN mv p3_lookup_table_1.dat-v4.1.2 /projects/e3sm/inputdata/atm/cam/physprops/

ENV USER=ghciocitester

RUN git config --global user.email "${USER}@${USER}.${USER}"
RUN git config --global user.name "${USER}"

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=America/Los_Angeles

ENV LANGUAGE=en_US:en \
    LANG=en_US.UTF-8

# TODO: move this to a separate image (i.e., above is "base", below is "full")?
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

COPY files.txt /app/files.txt
RUN /app/download.sh

# TODO: maybe add a test here or in the workflow?

ENTRYPOINT ["/bin/bash", "--rcfile", "/etc/profile", "-l"]
