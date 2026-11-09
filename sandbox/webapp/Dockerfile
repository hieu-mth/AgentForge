# Owner builds this offline-QA image manually, separate from any AI task.
# Use only the audited reference package manifest. No app source is copied.
FROM node:22-alpine
WORKDIR /opt/agentforge
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts \
    && chmod -R a+rX /opt/agentforge
USER 10001:10001
ENTRYPOINT ["/bin/sh"]
