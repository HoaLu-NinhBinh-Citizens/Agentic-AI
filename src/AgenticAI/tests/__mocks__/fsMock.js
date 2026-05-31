// Mock fs module for testing
module.exports = {
  promises: {
    readFile: jest.fn(),
    writeFile: jest.fn(),
    readdir: jest.fn(),
    mkdir: jest.fn(),
    unlink: jest.fn(),
    rename: jest.fn(),
    stat: jest.fn(),
    access: jest.fn(),
  },
  existsSync: jest.fn(),
  readFileSync: jest.fn(),
  writeFileSync: jest.fn(),
  readdirSync: jest.fn(),
  watch: jest.fn(),
  watchFile: jest.fn(),
  createReadStream: jest.fn(),
  createWriteStream: jest.fn(),
};
