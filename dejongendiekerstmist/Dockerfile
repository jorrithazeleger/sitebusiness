FROM node:22-alpine
WORKDIR /app
COPY package.json ./
COPY server.js ./
COPY lib ./lib
COPY scripts ./scripts
COPY public ./public
COPY content ./content
ENV NODE_ENV=production PORT=3000
# bestellingen en sleutels: koppel deze map aan blijvende opslag
VOLUME /app/data
EXPOSE 3000
USER node
CMD ["node", "server.js"]
