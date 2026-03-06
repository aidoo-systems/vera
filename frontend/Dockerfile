FROM node:20-alpine

WORKDIR /app

RUN addgroup -g 1001 vera && adduser -u 1001 -G vera -s /bin/sh -D vera

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN chown -R vera:vera /app

EXPOSE 3000

USER vera
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3000"]
