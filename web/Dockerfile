# Container build for the QuantumVerse web frontend.
# Runs on OpenShift's arbitrary-UID model: files owned by 1001, group 0,
# with group-writable .next for Next's runtime cache.

FROM registry.access.redhat.com/ubi9/nodejs-22:latest

WORKDIR /opt/app-root/src

COPY --chown=1001:0 package.json package-lock.json ./
RUN npm ci

COPY --chown=1001:0 . .
RUN npm run build && npm prune --omit=dev && chmod -R g+rwX .next

ENV NODE_ENV=production PORT=3000
EXPOSE 3000
CMD ["npm", "start"]
