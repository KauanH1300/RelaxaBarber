FROM grafana/grafana:12.4.0
USER root
RUN grafana cli --pluginsDir /opt/grafana-plugins plugins install alexanderzobnin-zabbix-app 6.2.1
ENV GF_PATHS_PLUGINS=/opt/grafana-plugins
USER 472
