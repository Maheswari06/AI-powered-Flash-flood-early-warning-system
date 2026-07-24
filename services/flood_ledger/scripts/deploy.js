// Deploy FloodLedger smart contract to local Hardhat network

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying FloodLedger with account:", deployer.address);
  console.log("Account balance:", (await deployer.provider.getBalance(deployer.address)).toString());

  // Deploy with 8800 bps (88%) payout threshold
  const FloodLedger = await ethers.getContractFactory("FloodLedger");
  const ledger = await FloodLedger.deploy(8800);
  await ledger.waitForDeployment();

  const address = await ledger.getAddress();
  console.log("FloodLedger deployed to:", address);

  // Deposit some test ETH for insurance pool
  const depositTx = await ledger.deposit({ value: ethers.parseEther("10.0") });
  await depositTx.wait();
  console.log("Deposited 10 ETH to insurance pool");

  // Write contract address to env
  const fs = require("fs");
  const envLine = `\nCONTRACT_ADDRESS=${address}\n`;
  try {
    fs.appendFileSync("../../.env", envLine);
    console.log("Contract address written to .env");
  } catch (e) {
    console.log("Set CONTRACT_ADDRESS=" + address + " in your .env file");
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
