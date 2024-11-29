FROM python

RUN mkdir -p /e3sm_diags_downloaded_data/tests/integration

COPY download_files.py /app/download_files.py
RUN chmod +x /app/download_files.py
RUN /app/download_files.py

ENTRYPOINT ["/bin/bash", "--rcfile", "/etc/profile", "-l"]
