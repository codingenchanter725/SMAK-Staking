import smartpy as sp
class Error:
    def make(s): return (s)

    NotAdmin                        = make("Access denied")
    AmountTooHigh                   = make("Amount is too high")
    AmountTooLow                    = make("Amount is too low")
    DupStakingOpt                   = make("A staking option with this Id already exists")
    NotStakingOpt                   = make("The staking option for this id does not exist")
    NeverStaked                     = make("Never staked on this contract")
    NeverUsedPack                   = make("Never staked using this pack")
    NotStaking                      = make("This stake doesn't exist")
    BalanceTooLow                   = make("Not enough tokens to unstake")
    StakingFlexRate                 = make("Can't update the staking flex rate with this function")
    NotOption                       = make("This option does not exist")
    NotAllowedFlex                  = make("Deleting the flex option is now allowed")


StakeLock = sp.TRecord(
    timestamp=sp.TTimestamp,
    period = sp.TInt,
    rate=sp.TNat,
    value=sp.TNat
)

StakeFlex = sp.TRecord(
    timestamp=sp.TTimestamp,
    value=sp.TNat,
    reward=sp.TNat,
    rate = sp.TNat
)

UserStakeFlexPack = sp.big_map(tkey=sp.TNat, tvalue =sp.TMap(sp.TAddress,  StakeFlex))

UserStakeLockPack = sp.big_map(
    tkey=sp.TAddress,
    tvalue=sp.TMap(
        sp.TNat,
        sp.TMap(
            sp.TNat,
            StakeLock)
    )
)

TotalReward = sp.big_map(tkey = sp.TAddress, tvalue = sp.TNat)

Options = sp.map(
    l = {sp.nat(0):sp.record(minStake = 0, maxStake = 1000000, stakingPeriod = 0, stakingPercentage = 20)},
    tkey=sp.TNat,
    tvalue= sp.TRecord(
            minStake=sp.TNat,
            maxStake=sp.TNat,
            stakingPeriod=sp.TInt,
            stakingPercentage=sp.TNat
        )
    )

def call(c, x):
    sp.transfer(x, sp.mutez(0), c)

# Storage:
# - FA12TokenContract: contract address of the FA12 related token
# - admin: contract admin address
# - reserve: rewards reserve address
# - userStakeLockPack: big map containing the staking lock information
# - userStakeFlexPack: big map containing the staking flex information
# - stakingOptions: map with the staking options information
# - votingContract: address of a future voting contract that is allowed to make updates on this contract
# - addressId: big map containing all the addresses of the flex stakers and their related id
# - maxValuesNb: the highest id in the addressId map
# - stakingHistory: map containing the staking history for a given time period
# - numberOfStakers: the number of users staking SMAK
# - redeemedRewards: big map containing the total of the redeemed rewards for each user
# - totalRedeemedRewards: the total number of redeemed rewards since the beginning
# - metadata: contract metadata

class FA12Staking_core(sp.Contract):
    def __init__(self, contract, admin, reserve, metadata_url, **kargs):
        self.init(
            FA12TokenContract=contract,
            admin=admin,
            reserve=reserve,
            userStakeLockPack=UserStakeLockPack,
            userStakeFlexPack=UserStakeFlexPack,
            stakingOptions=Options,
            votingContract = sp.none,
            addressId = sp.big_map(tkey = sp.TAddress, tvalue = sp.TNat),
            maxValuesNb = sp.nat(150),
            stakeFlexLength = sp.nat(0),
            stakingHistory = sp.big_map(l={sp.timestamp(0):0},tkey = sp.TTimestamp, tvalue = sp.TInt),
            numberOfStakers=sp.int(0),
            redeemedRewards = sp.big_map(tkey = sp.TAddress, tvalue = sp.TNat),
            totalRedeemedRewards = sp.nat(0),
            metadata = sp.big_map({"":metadata_url}),
            **kargs
        )

    # The function updateMetadata will update the metadata ipfs url
    # The function takes as parameter:
    # - the new metadata ipfs url in bytes
    @sp.entry_point
    def updateMetadata(self,params):
            sp.set_type(params, sp.TRecord(url = sp.TBytes))
            sp.verify_equal(sp.sender, self.data.admin, Error.NotAdmin)
            self.data.metadata[""] = params.url

    # The function updateReserve will update the reserve address
    # The function takes as parameter:
    # - the new reserve address
    @sp.entry_point
    def updateReserve(self, params):
        sp.set_type(params, sp.TRecord(reserve=sp.TAddress))
        sp.verify_equal(sp.sender, self.data.admin, Error.NotAdmin)
        self.data.reserve = params.reserve

    # The function updateAdmin will update the admin address
    # The function takes as parameter:
    # - the new admin address
    @sp.entry_point
    def updateAdmin(self, params):
        sp.set_type(params, sp.TRecord(admin=sp.TAddress))
        sp.verify_equal(sp.sender, self.data.admin, Error.NotAdmin)
        self.data.admin = params.admin
    
    # The function updateContract will update the address of the token contract
    # The function takes as parameter:
    # - the new token contract address
    @sp.entry_point
    def updateContract(self, params):
        sp.set_type(params, sp.TRecord(contract = sp.TAddress))
        sp.verify_equal(sp.sender, self.data.admin, Error.NotAdmin)
        self.data.FA12TokenContract = params.contract
    
    
    # The function updateVotingContract will update the address of the voting contract
    # The function takes as parameter:
    # - the new voting contract address
    @sp.entry_point
    def updateVotingContract(self, params):
        sp.set_type(params, sp.TRecord(contract = sp.TAddress))
        sp.verify_equal(sp.sender, self.data.admin, Error.NotAdmin)
        self.data.votingContract = sp.some(params.contract)
    
    # The function is_voting_contract checks if a given address matches the voting contract's one
    # The function takes as parameter:
    # - an address
    @sp.sub_entry_point
    def is_voting_contract(self, contract):
        sp.if self.data.votingContract.is_some():
            sp.result(self.data.votingContract.open_some() == contract)
        sp.else:
            sp.result(False)

    # The createStakingOption function is used to create a staking pack (period/APY). Only the admin can call this function
    # The function takes as parameters:
    # - the id of the staking parameters
    # - the staking rate
    # - the maximum staking amount per transaction
    # - the minimum staking amount per transaction
    # - the staking period
    @sp.entry_point
    def createStakingOption(self, params):
        sp.set_type(params, sp.TRecord(_id = sp.TNat, rate = sp.TNat, _max = sp.TNat, _min = sp.TNat, duration = sp.TInt).layout(("_id as id", ("rate", ("_max as max", ("_min as min", "duration"))))))
        sp.verify(~self.data.stakingOptions.contains(params._id), Error.DupStakingOpt)
        sp.verify(self.is_voting_contract(sp.sender) | (self.data.admin == sp.sender), Error.NotAdmin)
        option = sp.record(
            minStake = params._min,
            maxStake = params._max,
            stakingPeriod = params.duration,
            stakingPercentage = params.rate
        )
        self.data.stakingOptions[params._id] = option
    
    
    # The function updateStakingOptionRate will update the rate of a specified staking pack
    # The function takes as parameters:
    # - the staking pack id
    # - the staking pack new rate
    @sp.entry_point
    def updateStakingOptionRate(self, params):
        sp.set_type(params, sp.TRecord(_id = sp.TNat, rate = sp.TNat).layout(("_id as id", "rate")))
        sp.verify(self.is_voting_contract(sp.sender) | (self.data.admin == sp.sender), Error.NotAdmin)
        sp.verify(self.data.stakingOptions.contains(params._id), Error.NotStakingOpt)
        self.data.stakingOptions[params._id].stakingPercentage = params.rate


    # The function updateStakingOptionDuration will update the duration of the staking pack
    # The function takes as parameters:
    # - the staking pack id
    # - the staking pack new duration
    @sp.entry_point
    def updateStakingOptionDuration(self, params):
        sp.set_type(params, sp.TRecord(_id = sp.TNat, duration = sp.TInt).layout(("_id as id", "duration")))
        sp.verify(self.is_voting_contract(sp.sender) | (self.data.admin == sp.sender), Error.NotAdmin)
        sp.verify(self.data.stakingOptions.contains(params._id), Error.NotStakingOpt)
        sp.verify(params._id != sp.nat(0))
        self.data.stakingOptions[params._id].stakingPeriod = params.duration
    

    # The function updateStakingOptionMax will update the max a user can stake in one transaction
    # The function takes as parameters:
    # - the staking pack id
    # - the staking pack new max amount per transaction 
    @sp.entry_point
    def updateStakingOptionMax(self, params):
        sp.set_type(params, sp.TRecord(_id = sp.TNat, _max = sp.TNat).layout(("_id as id", "_max as max")))
        sp.verify(self.is_voting_contract(sp.sender) | (self.data.admin == sp.sender), Error.NotAdmin)
        sp.verify(self.data.stakingOptions.contains(params._id), Error.NotStakingOpt)
        self.data.stakingOptions[params._id].maxStake = params._max
    
    # The function updateStakingOptionMin will update the min a user can stake in one transaction
    # The function takes as parameters:
    # - the staking pack id
    # - the staking pack new min amount per transaction 
    @sp.entry_point
    def updateStakingOptionMin(self, params):
        sp.set_type(params, sp.TRecord(_id = sp.TNat, _min = sp.TNat).layout(("_id as id", "_min as min")))
        sp.verify(self.is_voting_contract(sp.sender) | (self.data.admin == sp.sender), Error.NotAdmin)
        sp.verify(self.data.stakingOptions.contains(params._id), Error.NotStakingOpt)
        self.data.stakingOptions[params._id].minStake = params._min
  
    @sp.entry_point
    def deleteStakingOption(self, params):
        sp.set_type(params, sp.TRecord(_id = sp.TNat))
        sp.verify(self.is_voting_contract(sp.sender) | (self.data.admin == sp.sender), Error.NotAdmin)
        sp.verify(params._id != 0, Error.NotAllowedFlex)
        sp.verify(self.data.stakingOptions.contains(params._id), Error.NotOption)
        del self.data.stakingOptions[params._id]
        
        
    @sp.entry_point
    def updateMaxValuesNb(self, params):
        sp.set_type(params, sp.TRecord(value = sp.TNat))
        sp.verify(self.is_voting_contract(sp.sender) | (self.data.admin == sp.sender), Error.NotAdmin)
        sp.verify(params.value != 0)
        self.data.maxValuesNb = params.value
        

class FA12Staking_methods(FA12Staking_core):
    
    # The function increments the number of stakers by 1 if there is a new users stakes SMAK on the contract
    # The function takes as parameter:
    # - user address
    def addStaker(self, addr):
        sp.if (~self.data.userStakeLockPack.contains(addr) & ~self.data.addressId.contains(addr)):
            self.data.numberOfStakers += 1
      
    # The function decrements the number of stakers by 1 if there is a user that unstakes his last stake from the contract
    # The function takes as parameter:
    # - user address  
    def delStaker(self, addr):
        sp.if (~self.data.userStakeLockPack.contains(addr) & ~self.data.addressId.contains(addr)):
            self.data.numberOfStakers -= 1
            
            
    # The stakeLock function will create a staking lock with the parameters of the specified pack
    # The function takes as parameters:
    # - the pack id
    # - the staking amount
    @sp.entry_point
    def stakeLock(self, params):
        sp.set_type(params, sp.TRecord(pack = sp.TNat, amount = sp.TNat))
        
        sp.verify(params.amount >= self.data.stakingOptions[params.pack].minStake, Error.AmountTooLow)
        sp.verify(params.amount <= self.data.stakingOptions[params.pack].maxStake, Error.AmountTooHigh)
        sp.verify(self.data.stakingOptions.contains(params.pack), Error.NotStakingOpt)
        
        # Transfer the staking amount from the address to the contract
        paramTrans = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
        paramCall = sp.record(from_=sp.sender, to_=self.data.reserve, value=params.amount)
        call(sp.contract(paramTrans ,self.data.FA12TokenContract ,entry_point="transfer").open_some(), paramCall)
        
        # Create the stake on the contract
        staking = sp.record(timestamp=sp.now.add_seconds(0), rate = self.data.stakingOptions[params.pack].stakingPercentage, period = self.data.stakingOptions[params.pack].stakingPeriod, value = params.amount)
        
        self.addStaker(sp.sender) # Increment the number of stakers on the contract by 1 if this is the user's first stake
        
        # Check if it is the first stake for the user and creates their staking big map
        sp.if ~self.data.userStakeLockPack.contains(sp.sender):
            self.data.userStakeLockPack[sp.sender] = sp.map({params.pack :sp.map(l= {sp.nat(0):staking})})
        
        # If not, update the current user's map
        sp.else:
            sp.if ~self.data.userStakeLockPack[sp.sender].contains(params.pack):
                self.data.userStakeLockPack[sp.sender][params.pack] = sp.map({sp.nat(0):staking})
            sp.else:
                index = sp.len(self.data.userStakeLockPack[sp.sender][params.pack])
                self.data.userStakeLockPack[sp.sender][params.pack][index] = staking

        self.data.stakingHistory[sp.now.add_seconds(0)] = sp.to_int(params.amount) # Update the staking history
      
      
    # The stakeFlex function will create a staking flex with the parameters of the current staking flex parameters
    # The function takes as parameter:
    # - The amount staked
    @sp.entry_point
    def stakeFlex(self, params):
        sp.set_type(params, sp.TRecord(amount = sp.TNat))
        
        sp.verify(params.amount >= self.data.stakingOptions[0].minStake, Error.AmountTooLow)
        sp.verify(params.amount <= self.data.stakingOptions[0].maxStake, Error.AmountTooHigh)
        
        # Transfer the staking amount from the address to the contract
        paramTrans = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
        paramCall = sp.record(from_=sp.sender, to_=self.data.reserve, value=params.amount)
        call(sp.contract(paramTrans ,self.data.FA12TokenContract ,entry_point="transfer").open_some(), paramCall)
        
        current_rate = self.data.stakingOptions[0].stakingPercentage 
        
        self.addStaker(sp.sender) # Increment the number of stakers on the contract by 1 if this is the user's first stake
        
        # Update the addressId map with the user if they are not already registered 
        id_ = sp.local("id_", sp.nat(0))
        sp.if ~self.data.addressId.contains(sp.sender):
            sp.if (self.data.userStakeFlexPack.contains(self.data.stakeFlexLength) & (sp.len(self.data.userStakeFlexPack[self.data.stakeFlexLength]) >= self.data.maxValuesNb)):
                self.data.stakeFlexLength += 1
            id_.value = self.data.stakeFlexLength
            self.data.addressId[sp.sender] = id_.value
        id_.value = self.data.addressId[sp.sender]

        # Check if it is the user's first stake, and if it is, creates the associate big map. If not, updates it.
        sp.if ~self.data.userStakeFlexPack.contains(id_.value):
            self.data.userStakeFlexPack[id_.value] = {sp.sender : sp.record(timestamp = sp.now.add_seconds(0), value = params.amount + sp.nat(0), reward = sp.nat(0), rate = current_rate) }
        sp.else :
            sp.if ~self.data.userStakeFlexPack[id_.value].contains(sp.sender):
                self.data.userStakeFlexPack[id_.value][sp.sender] = sp.record(timestamp = sp.now.add_seconds(0), value = params.amount + sp.nat(0), reward = sp.nat(0), rate = current_rate)
            sp.else:
                    self.updateStakingFlex(id_.value, sp.sender, params.amount)
        self.data.stakingHistory[sp.now.add_seconds(0)] = sp.to_int(params.amount) # Update the staking history

        
    # The updateStakingFlex function will add the amount to the stake and update the timestamp
    # The function takes as parameters:
    # - the address of the sender
    # - the amount the user wants to add to the staking
    def updateStakingFlex(self, id_, addr, amount):
        staking = self.data.userStakeFlexPack[id_][addr]
        staking.reward += self.getReward(sp.record(start = staking.timestamp, end = sp.now.add_seconds(0),  value = staking.value, rate = staking.rate))
        staking.value += amount
        staking.timestamp = sp.now.add_seconds(0)
        staking.rate = self.data.stakingOptions[0].stakingPercentage


    # The unstakeLock function will unstake a locked staking
    # The function takes as parameters:
    # - the staking pack
    # - the index of the staking
    @sp.entry_point
    def unstakeLock(self, params):
        sp.set_type(params, sp.TRecord(pack=sp.TNat, index=sp.TNat))
        
        sp.verify(self.data.userStakeLockPack.contains(sp.sender), Error.NeverStaked)
        sp.verify(self.data.userStakeLockPack[sp.sender].contains(params.pack), Error.NeverUsedPack)
        sp.verify(self.data.userStakeLockPack[sp.sender][params.pack].contains(params.index), Error.NotStaking)
        
        staking = self.data.userStakeLockPack[sp.sender][params.pack][params.index]
        
        # Check if the staking lock period is fulfilled, if it is the case, the user receive their rewards while unstaking, if not, they only unstake their tokens.
        sp.if staking.timestamp.add_seconds(staking.period) < sp.now:
            self.unlockWithReward(sp.record(pack = params.pack, index = params.index, staking = staking))
        sp.else:
            self.unlockWithoutReward(sp.record(pack = params.pack, index = params.index, staking = staking))
           
        # Update the user's staking map 
        sp.if sp.len(self.data.userStakeLockPack[sp.sender][params.pack]) == 0:
            del self.data.userStakeLockPack[sp.sender][params.pack]
            sp.if sp.len(self.data.userStakeLockPack[sp.sender]) == 0:
                del self.data.userStakeLockPack[sp.sender]
                
        self.delStaker(sp.sender) # If it was the last user stake on the contract, update the number of total stakers.
        
        
            
    # The unlockWithReward function will send the tokens back to the user with the rewards
    # The function takes as parameters:
    # - the staking pack
    # - the index of the staking
    @sp.sub_entry_point
    def unlockWithReward(self, params):
        sp.set_type(params, sp.TRecord(pack = sp.TNat, index = sp.TNat, staking = StakeLock))
        
        amount = params.staking.value 
        reward = self.getReward(sp.record(start = params.staking.timestamp, end = params.staking.timestamp.add_seconds(params.staking.period), value = params.staking.value, rate = params.staking.rate))
        amount += reward
        
        # Send the token back + the reward amount from the reserve to the user
        paramTrans = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
        paramCall = sp.record(from_=self.data.reserve, to_=sp.sender, value=amount)
        call(sp.contract(paramTrans, self.data.FA12TokenContract, entry_point="transfer").open_some(), paramCall)
        
        self.updateRedeemedRewards(sp.sender, reward) # Update user's staking map
        self.data.stakingHistory[sp.now.add_seconds(0)] = -1 * sp.to_int(amount) # update staking history
        
        del self.data.userStakeLockPack[sp.sender][params.pack][params.index]
        
    
    # The unlockWithoutReward function will send the tokens back to the user without the reward
    # The function takes as parameters:
    # - the staking pack
    # - the index of the staking
    # - the staking information
    @sp.sub_entry_point
    def unlockWithoutReward(self, params):
        sp.set_type(params, sp.TRecord(pack = sp.TNat, index = sp.TNat, staking = StakeLock))
        amount = params.staking.value
        
        # Send the tokens back from the reserve to the reserve to the user
        paramTrans = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
        paramCall = sp.record(from_=self.data.reserve, to_=sp.sender, value=amount)
        call(sp.contract(paramTrans, self.data.FA12TokenContract,entry_point="transfer").open_some(), paramCall)
        
        self.data.stakingHistory[sp.now.add_seconds(0)] = -1 * sp.to_int(amount) # Update staking history
        del self.data.userStakeLockPack[sp.sender][params.pack][params.index]
        
        
    # The function unstakeFlex will send the specified amount of tokens to the user
    # The function takes as parameter
    # - the amount to unstake
    @sp.entry_point
    def unstakeFlex(self, params):
        sp.set_type(params, sp.TRecord(amount = sp.TNat))
        id_ = self.data.addressId[sp.sender]
        sp.verify(self.data.userStakeFlexPack[id_].contains(sp.sender), Error.NeverStaked)
        sp.verify(self.data.userStakeFlexPack[id_][sp.sender].value >= params.amount, Error.BalanceTooLow)
        
        # Send the tokens back from the reserve to user's address
        paramTrans = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
        paramCall = sp.record(from_=self.data.reserve, to_=sp.sender, value=params.amount)
        call(sp.contract(paramTrans, self.data.FA12TokenContract, entry_point="transfer").open_some(), paramCall)
        
        # Update user's staking flex map
        staking = self.data.userStakeFlexPack[id_][sp.sender]
        staking.reward += self.getReward(sp.record(start = staking.timestamp, end = sp.now.add_seconds(0), value = staking.value, rate = staking.rate))
        staking.value = sp.as_nat(staking.value - params.amount) 
        staking.timestamp = sp.now.add_seconds(0)
        staking.rate = self.data.stakingOptions[0].stakingPercentage
        
        self.data.stakingHistory[sp.now.add_seconds(0)] = -1 * sp.to_int(params.amount) # Update staking history
 
        self.delStaker(sp.sender) # If it was the last user stake on the contract, update the number of total stakers.

  

    # The function claimRewardFlex will send the rewards of a staking flex to the user
    # the function takes no parameter
    @sp.entry_point
    def claimRewardFlex(self):
        sp.verify(self.data.addressId.contains(sp.sender), Error.NeverStaked)
        id_ = self.data.addressId[sp.sender]
        
        sp.verify(self.data.userStakeFlexPack[id_].contains(sp.sender), Error.NeverStaked)
        
        staking = self.data.userStakeFlexPack[id_][sp.sender] 
        
        self.data.userStakeFlexPack[id_][sp.sender].reward += self.getReward(sp.record(start = staking.timestamp, end = sp.now.add_seconds(0), value = staking.value, rate = staking.rate))
        
        # Send the user's reward from the reserve to to the user's address
        paramTrans = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
        paramCall = sp.record(from_=self.data.reserve, to_=sp.sender, value=self.data.userStakeFlexPack[id_][sp.sender].reward)
        call(sp.contract(paramTrans ,self.data.FA12TokenContract ,entry_point="transfer").open_some(), paramCall)
       
        # Update user's staking flex map
        sp.if staking.value == 0:
            del self.data.userStakeFlexPack[id_][sp.sender]
            sp.if self.data.stakeFlexLength !=  id_:
                newAdd = sp.local("newAdd", sp.sender)
                sp.for i in self.data.userStakeFlexPack[self.data.stakeFlexLength].keys():
                    newAdd.value = i
                self.data.userStakeFlexPack[id_][newAdd.value] = self.data.userStakeFlexPack[self.data.stakeFlexLength][newAdd.value]
                self.data.addressId[newAdd.value] = id_
                del self.data.userStakeFlexPack[self.data.stakeFlexLength][newAdd.value]
                del self.data.addressId[sp.sender]
                sp.if sp.len(self.data.userStakeFlexPack[self.data.stakeFlexLength])== 0:
                    del self.data.userStakeFlexPack[self.data.stakeFlexLength]
                    self.data.stakeFlexLength = sp.as_nat(self.data.stakeFlexLength - 1)
            sp.else:
                sp.if sp.len(self.data.userStakeFlexPack[self.data.stakeFlexLength])== 0:
                    del self.data.userStakeFlexPack[self.data.stakeFlexLength]
                    del self.data.addressId[sp.sender]
                sp.if self.data.stakeFlexLength > 0:
                    self.data.stakeFlexLength = sp.as_nat(self.data.stakeFlexLength - 1)
        sp.else:
            self.updateRedeemedRewards(sp.sender, staking.reward)
            staking.reward = sp.as_nat(0) 
            staking.timestamp = sp.now.add_seconds(0)
            staking.rate = self.data.stakingOptions[0].stakingPercentage
        self.delStaker(sp.sender) # If it was the last user stake on the contract, update the number of total stakers.


    # The function will compute the rewards for a specified value during a period at a certain rate
    # The function takes as parameters:
    # - the starting timestamp
    # - the ending timestamp
    # - the value of the staking
    # - the rate of the staking
    def getReward(self, params):
        sp.set_type(params, sp.TRecord(start=sp.TTimestamp, end = sp.TTimestamp, value= sp.TNat, rate=sp.TNat))
        k = sp.nat(10000000000)
        period = params.end - params.start
        timeRatio = k * sp.as_nat(period) / sp.as_nat(sp.timestamp(0).add_days(365) - sp.timestamp(0))
        reward = timeRatio * params.rate
        reward *= params.value
        reward /= k*100
        return reward
        
    # The function will update the redeemed rewards map
    # The function takes as parameters:
    # - address of the user that redeemed their rewards
    # - amount of rewards
    def updateRedeemedRewards(self, addr, value):
        sp.if self.data.redeemedRewards.contains(addr):
            self.data.redeemedRewards[addr] = self.data.redeemedRewards[addr] + value
        sp.else:
            self.data.redeemedRewards[addr] = value
            
        self.data.totalRedeemedRewards += value
    
    # The function will compute the rewards for a given list of users and update their flex rate accordingly to the new one
    # The function takes as parameters:
    # - the id of the batch of users to update
    @sp.entry_point
    def updateStakingFlexRate(self, params):
        sp.set_type(params, sp.TRecord(id_=sp.TNat))
        
        sp.verify(sp.sender == self.data.admin, Error.NotAdmin)

        sp.for i in self.data.userStakeFlexPack[params.id_].keys():
            staking = self.data.userStakeFlexPack[params.id_][i]
            staking.reward += self.getReward(sp.record(start = staking.timestamp, end = sp.now.add_seconds(0), value = staking.value, rate = staking.rate))
            staking.timestamp = sp.now.add_seconds(0)
            staking.rate = self.data.stakingOptions[0].stakingPercentage
        
              
class FA12Staking(FA12Staking_core, FA12Staking_methods):
    def __init__(self, contract, admin, reserve, metadata_url):
        FA12Staking_core.__init__(self, contract, admin, reserve,metadata_url)

            


@sp.add_test(name="Minimal")
def test():
    scenario = sp.test_scenario()
    scenario.h1("FA1.2 Staking contract")
    scenario.table_of_contents()

    # sp.test_account generates ED25519 key-pairs deterministically:
    admin = sp.test_account("Administrator")
    alice = sp.test_account("Alice")
    bob = sp.test_account("Robert")
    reserve = sp.test_account("Reserve")
    new_reserve = sp.test_account("New_Reserve")
    oscar = sp.test_account("Oscar")
    

    # Let's display the accounts:
    scenario.h1("Accounts")
    scenario.show([admin, alice, bob, reserve, new_reserve, oscar])

    scenario.h1("Initialize the contract")
    contract = sp.address("KT1TezoooozzSmartPyzzSTATiCzzzwwBFA1")
    voting_contract = sp.address("KT1TezoooozzSmartPyzzSTATiCzzzwwBFAA")
    metadata_url = sp.utils.bytes_of_string("ipfs://Qmd24eKvMaYzBxbKEH6kr6nnnHMCCchntVprK3NJJfVvky")
    c1 = FA12Staking(contract, admin.address, reserve.address, metadata_url)
    scenario += c1

    scenario.h1("Tests")
    scenario.h2("Updating FA12TokenContract")
    scenario.h3("Alice tries to update the state variable but does not succeed")
    scenario += c1.updateContract(contract=sp.address("KT1Tezooo3zzSmartPyzzSTATiCzzzseJjWC")).run(sender=alice, valid=False)
    scenario.h3("Admin updates the state variable")
    scenario += c1.updateContract(contract=sp.address("KT1Tezooo3zzSmartPyzzSTATiCzzzseJjWC")).run(sender=admin)

    scenario.h2("Updating reserve")
    scenario.h3("Alice tries to update the state variable but does not succeed")
    scenario += c1.updateReserve(reserve = new_reserve.address).run(sender = alice, valid = False)
    scenario.h3("Admin updates the state variable")
    scenario += c1.updateReserve(reserve = new_reserve.address).run(sender = admin)
    
    scenario.h2("Creating a new staking option")
    scenario.h3("Alice tries to create a new staking option but does not succeed")
    scenario += c1.createStakingOption(_id = 0, rate = 20, _max = 1000000000000, _min = 0, duration = 0).run(sender = alice, valid = False)
    scenario.h3("Admin creates a new staking option that already exists")
    scenario += c1.createStakingOption(_id = 0, rate = 20, _max = 1000000000000, _min = 0, duration = 0).run(sender = admin, valid = False)
    scenario.h3("Admin creates a new staking option")
    scenario += c1.createStakingOption(_id = 1, rate = 20, _max = 1000000000000, _min = 10, duration = 31536000).run(sender = admin)
    scenario.h3("Admin creates a new staking option")
    scenario += c1.createStakingOption(_id = 2, rate = 20, _max = 1000000000000, _min = 10, duration = 31536000).run(sender = admin)
    
    scenario.h2("Updating MaxStake")
    scenario.h3("Alice tries to update the state variable but does not succeed")
    scenario += c1.updateStakingOptionMax(_id = 0, _max = 1000000).run(sender = alice, valid = False)
    scenario.h3("Admin updates the state variable")
    scenario += c1.updateStakingOptionMax(_id = 0, _max = 1000000).run(sender = admin)

    scenario.h2("Updating MinStake")
    scenario += c1.updateStakingOptionMin(_id = 0, _min = 1000).run(sender = alice, valid = False)
    scenario.h3("Admin updates the state variable")
    scenario += c1.updateStakingOptionMin(_id = 0, _min = 1000).run(sender = admin)

    scenario.h2("Updating staking duration")
    scenario += c1.updateStakingOptionDuration(_id = 1, duration = 10000).run(sender = alice, valid = False)
    scenario.h3("Admin updates the state variable")
    scenario += c1.updateStakingOptionDuration(_id = 1, duration = 10000).run(sender = admin)
    
    scenario.h2("Updating map max values number")
    scenario.h3("Admin updates the max value number to 0 but it does not work")
    scenario += c1.updateMaxValuesNb(value=0).run(sender = admin, valid = False)
    scenario.h3("Alice updates the max value number but she is not admin")
    scenario += c1.updateMaxValuesNb(value=1).run(sender = alice, valid = False)
    scenario.h3("Admin updates the max value number")
    scenario += c1.updateMaxValuesNb(value=2).run(sender = admin)
    
    scenario.h3("Admin tries to set a duration for the staking flex pack but fails")
    scenario += c1.updateStakingOptionDuration(_id = 0, duration = 10000).run(sender = admin, valid = False)

    scenario.h2("Updating staking rate")
    scenario.h3("Alice tries to update a staking pack rate")
    scenario += c1.updateStakingOptionRate(_id = 1, rate = 8).run(sender = alice, valid = False)
    scenario.h3("Admin updates a staking pack rate")
    scenario += c1.updateStakingOptionRate(_id = 1, rate = 8).run(sender = admin)

    scenario.h2("Updating voting contract")
    scenario.h3("Alice tries to update the voting contract")
    scenario += c1.updateVotingContract(contract= voting_contract).run(sender = alice, valid = False)
    scenario.h3("Admin updates the voting contract")
    scenario += c1.updateVotingContract(contract=voting_contract).run(sender = admin)
    
    scenario.h2("Updating Admin")
    scenario.h3("Alice tries to update the state variable but does not succeed")
    scenario += c1.updateAdmin(admin=alice.address).run(sender=alice, valid=False)
    scenario.h3("Admin updates the state variable")
    scenario += c1.updateAdmin(admin=alice.address).run(sender=admin)

    scenario.h2("Staking flex")
    scenario.h3("Alice tries to stake flex and succeeds")
    scenario += c1.stakeFlex(amount = 10000).run(sender=alice)
    scenario.h3("Alice tries to stake more tokens and succeds")
    scenario += c1.stakeFlex(amount = 10100).run(sender = alice)
    
    scenario.h2("Changing the staking flex's rate")
    scenario.h3("Alice updates the flex rate for the addresses at the id 0 and succeeds")
    scenario += c1.updateStakingFlexRate(id_=0).run(sender = alice, now = sp.timestamp(int(31536000/2)))
    scenario.h3("Trying to update the staking flex rate but is not admin nor voting contract")
    scenario += c1.updateStakingFlexRate(id_=0).run(sender = bob, valid = False, now = sp.timestamp(int(31536000/2)))
    
    scenario.h3("Alice tries to stake too few tokens and fails")
    scenario += c1.stakeFlex(amount = 1).run(sender = alice, valid = False)
    scenario.h3("Alice tries to stake too much tokens and fails")
    scenario += c1.stakeFlex(amount = 1000001).run(sender = alice, valid = False)
    scenario.h3("Alice tries to stake more tokens and succeds")
    scenario += c1.stakeFlex(amount = 10000).run(sender = alice)
    scenario.h3("Admin tries to stake tokens and succeeds")
    scenario += c1.stakeFlex(amount = 10000).run(sender = admin)
    scenario.h3("Oscar tries to stake tokens and succeeds")
    scenario += c1.stakeFlex(amount = 10000).run(sender = oscar)
    
    scenario.h2("Unstaking flex")
    scenario.h3("Alice tries to unstake some of her tokens after 1 year and succeds")
    scenario += c1.unstakeFlex(amount = 20100).run(sender = alice, now = sp.timestamp(31536000))
    scenario.h3("Alice tries to unstake tokens even though she has already unstaked everything")
    scenario += c1.unstakeFlex(amount = 10000).run(sender = alice, now = sp.timestamp(31536000))
    scenario.h3("Admin tries to unstake some of her tokens after 1 year and succeeds")
    scenario += c1.unstakeFlex(amount = 10000).run(sender = admin, now = sp.timestamp(31536000))
    scenario.h3("Oscar tries to unstake some of her tokens after 1 year and succeeds")
    scenario += c1.unstakeFlex(amount = 10000).run(sender = oscar, now = sp.timestamp(31536000))
    scenario.h3("Bob tries to unstake but he never staked")
    scenario += c1.unstakeFlex(amount = 1000).run(sender = bob, valid = False)
    
    
    scenario.h2("Staking flex reward claiming")
    scenario.h3("Alice claims her rewards for her past stakings and succeeds (watch console)")
    scenario += c1.claimRewardFlex().run(sender = alice, now = sp.timestamp(2*31536000))
    scenario.h3("Admin claims her rewards for her past stakings and succeeds (watch console)")
    scenario += c1.claimRewardFlex().run(sender = admin, now = sp.timestamp(2*31536000))
    scenario.h3("Oscar claims her rewards for her past stakings and succeeds (watch console)")
    scenario += c1.claimRewardFlex().run(sender = oscar, now = sp.timestamp(2*31536000))
    scenario.h3("Alice tries to claim her rewards again but since she has no token staked she gets no rewards (watch console)")
    scenario += c1.claimRewardFlex().run(sender = alice, now = sp.timestamp(3*31536000), valid = False)
    scenario.h3("Bob tries to claim rewards but he never stake and he fails")
    scenario += c1.claimRewardFlex().run(sender = bob, valid = False)
    
    
    scenario.h2("Staking lock")
    scenario.h3("Alice tries to stake using the locked pack 1 and succeeds")
    scenario += c1.stakeLock(pack = 1, amount = 10000).run(sender = alice, now = sp.timestamp(10))
    scenario.h3("Alice tries to create another stake for the same pack and succeds")
    scenario += c1.stakeLock(pack = 1, amount = 10000).run(sender = alice)
    scenario.h3("Alice tries to stake too few tokens for the pack 1 and fails")
    scenario += c1.stakeLock(pack = 1, amount = 1).run(sender = alice, valid = False)
    scenario.h3("Alice tries to stake too much tokens for the pack 1 and fails")
    scenario += c1.stakeLock(pack = 1, amount = 1000000000001).run(sender = alice, valid = False)
    scenario.h3("Alice tries to stake using the locked pack 3 that doesn't exist and fails")
    scenario += c1.stakeLock(pack = 3, amount = 100000).run(sender = alice, valid = False)
    scenario.h3("Admin tries to stake using the locked pack 1 and succeds")
    scenario += c1.stakeLock(pack = 1, amount = 10000).run(sender = admin)
    
    scenario.h2("Deleting a staking option")
    scenario.h3("Bob tries to delete an option but is not admin")
    c1.deleteStakingOption(_id=1).run(sender = bob, valid = False)
    scenario.h3("Alice tries to delete the flex option")
    c1.deleteStakingOption(_id=0).run(sender = alice, valid = False)
    scenario.h3("Alice tries to delete a lock option and succeeds")
    c1.deleteStakingOption(_id=1).run(sender = alice)
    scenario.h3("Alice tries to delete a lock option that was already deleted")
    c1.deleteStakingOption(_id=1).run(sender = alice, valid = False)
    scenario.h3("Alice tries to delete a lock option that does not exist")
    c1.deleteStakingOption(_id=3).run(sender = alice, valid = False)
    
    
    scenario.h2("Unstaking lock")
    scenario.h3("Alice tries to unstake her tokens before the end of the locking period and does not get her rewards (watch console)")
    scenario += c1.unstakeLock(pack = 1, index = 0).run(sender = alice, now = sp.timestamp(31535999))
    scenario.h3("Alice tries to unstake her tokens after the locking period and gets here rewards (watch console)")
    scenario += c1.unstakeLock(pack = 1, index = 1).run(sender = alice, now = sp.timestamp(31536011))
    scenario.h3("Alice tries to unstake and already unstaked staking and fails")
    scenario += c1.unstakeLock(pack = 1, index = 0).run(sender = alice, now = sp.timestamp(31536001), valid = False)
    scenario.h3("Alice tries to unstake a pack she never used and fails")
    scenario += c1.unstakeLock(pack = 2, index = 0).run(sender = alice, valid = False)
    scenario.h3("Alice tries to unstake a pack that doesn't exist and fails")
    scenario += c1.unstakeLock(pack = 3, index = 0).run(sender = alice, valid = False)
    scenario.h3("Bob tries to unstake but he has never staked and fails")
    scenario += c1.unstakeLock(pack = 1, index = 0).run(sender = bob, valid = False)
    scenario.h3("Admin unstakes his tokens after the end of the lock pack")
    scenario += c1.unstakeLock(pack = 1, index = 0).run(sender = admin)

    
    scenario.h2("Attempt to update metadata")
    c1.updateMetadata(url = sp.bytes("0x00")).run(sender = alice)
    scenario.verify(c1.data.metadata[""] == sp.bytes("0x00"))