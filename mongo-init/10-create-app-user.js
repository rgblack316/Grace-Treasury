// Runs once, only when MongoDB creates a brand-new, empty database (new installs).
// Existing installs get the same account from ./enable-db-auth.sh instead.
// Creates the account the Grace Treasury backend signs in with: read/write on its own
// database only, no administrative rights.
const user = process.env.MONGO_APP_USERNAME;
const pwd = process.env.MONGO_APP_PASSWORD;
const dbName = process.env.APP_DB_NAME || "church_treasury";
if (user && pwd) {
  db.getSiblingDB("admin").createUser({ user, pwd, roles: [{ role: "readWrite", db: dbName }] });
  print(`Created Grace Treasury app account '${user}' (readWrite on ${dbName})`);
} else {
  print("MONGO_APP_USERNAME/MONGO_APP_PASSWORD not set; no app account created");
}
