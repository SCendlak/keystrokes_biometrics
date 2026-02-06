FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# Expose Vite dev server port; --host 0.0.0.0 so it's reachable from host
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
