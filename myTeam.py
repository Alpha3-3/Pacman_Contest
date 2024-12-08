# myTeam.py
# ---------

from captureAgents import CaptureAgent
import random, time, util
from game import Directions
import game
import math

#################
# Team creation #
#################

def createTeam(firstIndex, secondIndex, isRed,
               first='DynamicAgent', second='DynamicAgent'):
  """
  This function should return a list of two agents that will form the
  team, initialized using firstIndex and secondIndex as their agent
  index numbers.  isRed is True if the red team is being created, and
  will be False if the blue team is being created.

  As a potentially helpful development aid, this function can take
  additional string-valued keyword arguments ("first" and "second" are
  such arguments in the case of this function), which will come from
  the --redOpts and --blueOpts command-line arguments to capture.py.
  For the nightly contest, however, your team will be created without
  any extra arguments, so you should make sure that the default
  behavior is what you want for the nightly contest.
  """
  return [DynamicAgent(firstIndex, secondIndex), DynamicAgent(secondIndex, firstIndex)]

##########
# Agents #
##########

class DynamicAgent(CaptureAgent):
  """
  A dynamic agent that switches between offensive and defensive roles
  based on the game state, and collaborates with its teammate.
  My plan is:
  Agents should consider the offensive and defensive behavior depending on the current status.
  It should consider offense if:
    In good position (easy score, close food, enemy far away)
    Can get power capsule
  Should consider defense if:
    Need to intercept an enemy HVT
    My team is winning and it is possible to seal the entire map
    It is easy to intercept an enemy target (even if it is not a HVT)
  By HVT, I mean
    An agent eaten a lot of dots, or
    an agent that has enough time to do so
  Should also consider the collaboration between agents
  There are some other detailed behavior, which will be introduced later
  """

  # Shared information among agents
  teammateInfo = {}

  def __init__(self, index, teammateIndex):
    CaptureAgent.__init__(self, index)
    self.teammateIndex = teammateIndex
    self.currentRole = 'Offense'  # Initial role; can be 'Offense' or 'Defense' or 'ReturnHome' later
    self.hvtThreshold = 3  # Number of dots carried to be considered HVT
    self.target = None

  def registerInitialState(self, gameState):
    """
    Initializes the agent's state.
    """
    CaptureAgent.registerInitialState(self, gameState)
    self.start = gameState.getAgentPosition(self.index)
    self.walls = gameState.getWalls()
    self.width = self.walls.width
    self.height = self.walls.height
    self.midWidth = self.width // 2
    self.lastTeammatePos = None
    self.teammateTarget = None

  def chooseAction(self, gameState):
    """
    Chooses the best action to take based on current game state.
    """
    # Update role based on game state
    self.updateRole(gameState)

    # Get current pos
    myPos = gameState.getAgentPosition(self.index)

    # Update teammate info
    self.updateTeammateInfo(gameState)

    # Store current pos and target
    DynamicAgent.teammateInfo[self.index] = {'position': myPos, 'target': self.target}

    # Get legal actions
    actions = gameState.getLegalActions(self.index)

    # Eval actions and pick the best
    values = [self.evaluate(gameState, a) for a in actions]
    maxValue = max(values)
    bestActions = [a for a, v in zip(actions, values) if v == maxValue]

    # After eval, update the stored target
    DynamicAgent.teammateInfo[self.index]['target'] = self.target

    # Return a random choice among the best actions
    return random.choice(bestActions)

  def updateRole(self, gameState):
    """
    Updates the agent's role between offense and defense dynamically, specifically:
    1. hvtThreshold is a suggestion, not absolute. Even if above threshold, if safe, continue to eat.
       Also, if below threshold but in danger, return home.
    2. When deciding to defend while winning, consider if you (and your team) can reliably hold all remaining food.
    3. If there is an invader, only switch to defense if you are needed. If one agent can handle the invader alone, the other can keep attacking.
    """

    myState = gameState.getAgentState(self.index)
    myPos = myState.getPosition()
    foodLeft = len(self.getFood(gameState).asList())
    score = self.getScore(gameState)
    timeLeft = gameState.data.timeleft / 4  # Time left in moves, considering all agents
    enemies = [gameState.getAgentState(i) for i in self.getOpponents(gameState)]
    invaders = [a for a in enemies if a.isPacman and a.getPosition() is not None]

    # Check High-Value Target conditions:
    # Even if carrying a lot of food (>= hvtThreshold), consider staying offensive if safe.
    # Conversely, even if not at threshold, return home if staying out is too risky.
    # HVT process in isSafeToKeepEating
    # If above threshold, consider returning home unless it's safe to keep eating.
    if not self.isSafeToKeepEating(gameState):
      self.currentRole = 'ReturnHome'
      return

    # No food, go home
    if foodLeft == 0:
      self.currentRole = 'ReturnHome'

    # If winning, consider switching to defense if we can hold all remaining food effectively.
    # "canHoldAllFood" is a heuristic that checks if we (with teammates) can reliably prevent enemy from scoring.
    if score >= 1 and self.canHoldAllFood(gameState) and myState.numCarrying < 1:
      self.currentRole = 'Defense'
      return

    # If there are invaders, decide whether to defend or let the teammate handle it.
    # "whoShouldDefend" checks if a single agent (maybe the closest one) can handle the invader alone.
    # If yes, and if we are not that agent, we can remain on offense.
    interceptor = None
    if len(invaders) > 0:
      interceptor = self.whoShouldDefend(gameState, invaders)
    if interceptor is None:
      # No single agent can handle all invaders alone, or no invaders at all.
      # We are needed to defend if there are invaders.
      if len(invaders) > 0:
        self.currentRole = 'Defense'
        return
    elif interceptor == self.index:
      # This agent is the one who must intercept the invaders alone
      self.currentRole = 'Defense'
      return
    # If interceptor is another teammate, they can handle it, so we don't switch to defense.
    # Continue with other checks.


  # If time is running out, consider returning home.
    homeBoundary = self.getHomeBoundary(gameState)
    if len(homeBoundary) > 0:
      homeDistances = [self.getMazeDistance(myPos, h) for h in homeBoundary]
      closestHomeDist = min(homeDistances) if homeDistances else float('inf')
    if timeLeft < closestHomeDist + 4 and self.currentRole != 'Defense':
      self.currentRole = 'ReturnHome'
      return

    # Default to offense if none of the above conditions are met
    self.currentRole = 'Offense'

  def updateTeammateInfo(self, gameState):
    """
    Updates the stored information about teammate's position and target.
    """
    teammateData = DynamicAgent.teammateInfo.get(self.teammateIndex, None)
    if teammateData:
      self.lastTeammatePos = teammateData['position']
      self.teammateTarget = teammateData['target']
    else:
      self.lastTeammatePos = gameState.getAgentPosition(self.teammateIndex)
      self.teammateTarget = None

  def evaluate(self, gameState, action):
    """
    Computes a linear combination of features and feature weights.
    """
    features = self.getFeatures(gameState, action)
    weights = self.getWeights(gameState, action)
    return features * weights

  def getFeatures(self, gameState, action):
    """
    Returns a dictionary of features for the state.
    """
    features = util.Counter()
    successor = self.getSuccessor(gameState, action)

    myState = successor.getAgentState(self.index)
    myPos = myState.getPosition()

    # Compute the distance to the nearest food
    foodList = self.getFood(successor).asList()
    features['successorScore'] = -len(foodList)  # Score is the number of food left

    # If in offense role
    if self.currentRole == 'Offense':
      if len(foodList) > 0:
        # Divide food among agents
        myFoods = self.getAssignedFoods(successor)
        if len(myFoods) > 0:
          minDistance = min([self.getMazeDistance(myPos, food) for food in myFoods])
          features['distanceToFood'] = minDistance
          # Set target to closest food
          closestFood = min(myFoods, key=lambda food: self.getMazeDistance(myPos, food))
          self.target = closestFood
        else:
          # No assigned foods, just pick the closest food
          minDistance = min([self.getMazeDistance(myPos, food) for food in foodList])
          features['distanceToFood'] = minDistance
          closestFood = min(foodList, key=lambda food: self.getMazeDistance(myPos, food))
          self.target = closestFood

      # Avoid enemies
      enemies = [successor.getAgentState(i) for i in self.getOpponents(successor)]
      defenders = [a for a in enemies if not a.isPacman and a.getPosition() != None and a.scaredTimer <= 1]
      if len(defenders) > 0:
        distances = [self.getMazeDistance(myPos, a.getPosition()) for a in defenders]
        minDefenderDist = min(distances)
        if minDefenderDist <= 5:
          features['enemyDistance'] = minDefenderDist

      # Consider power capsules
      # Rather complicated here. The goal is:
      # if A1 finds out that there is a friendly HVT with conditions met,
      # and it is the closest agent to a capsule and is possible to get it,
      # then A1 should go for capsule (to protect the friendly HVT, where A1 could also just be the HVT itself)
      capsules = self.getCapsules(successor)

      # Identify if there's a friendly HVT under threat (including itself)
      # Conditions: Has numCarrying >= hvtThreshold and at least one defender is around
      friendlyStates = [(allyIndex, successor.getAgentState(allyIndex)) for allyIndex in self.getTeam(successor)]
      HVTs = [ (allyIndex, state) for (allyIndex, state) in friendlyStates if state.numCarrying >= self.hvtThreshold ]

      if len(capsules) > 0 and len(defenders) > 0 and len(HVTs) > 0:
        # Check if any friendly agent (including this one) can effectively reach a capsule quickly
        # We'll determine who is closest to each capsule among the friendly agents.

        # Get positions of all teammates that are observable
        friendlyPositions = {allyIndex: state.getPosition() for (allyIndex, state) in friendlyStates if state.getPosition() is not None}

        bestCapsuleDistance = float('inf')  # Track the closest capsule distance if this agent is the chosen one

        for cap in capsules:
          # For each capsule, find which friendly agent can get there fastest
          distancesToCap = []
          for allyIndex, allyPos in friendlyPositions.items():
            dist = self.getMazeDistance(allyPos, cap)
            distancesToCap.append((allyIndex, dist))

          # Find the closest friendly agent to this capsule
          if distancesToCap:
            closestAllyIndex, closestDist = min(distancesToCap, key=lambda x: x[1])

            # If I am the closest ally to this capsule, consider going for it
            if closestAllyIndex == self.index and closestDist < bestCapsuleDistance:
              bestCapsuleDistance = closestDist

        # If we found a capsule for which we are the closest friendly agent, record this feature
        if bestCapsuleDistance < float('inf'):
          features['distanceToCapsule'] = bestCapsuleDistance

    elif self.currentRole == 'Defense':
        # Compute distance to invaders
        enemies = [successor.getAgentState(i) for i in self.getOpponents(successor)]
        invaders = [a for a in enemies if a.isPacman and a.getPosition() != None]
        features['numInvaders'] = len(invaders)
        if len(invaders) > 0:
          # Identify HVT among invaders
          hvtInvaders = [a for a in invaders if a.numCarrying >= self.hvtThreshold]
          if len(hvtInvaders) > 0:
            # Prioritize HVT invaders
            distances = [self.getMazeDistance(myPos, a.getPosition()) for a in hvtInvaders]
            minInvaderDist = min(distances)
            features['invaderDistance'] = minInvaderDist

            # Consider intercepting before they reach capsules
            capsules = self.getCapsulesYouAreDefending(successor)
            if len(capsules) > 0:
              distancesToCapsules = [self.getMazeDistance(a.getPosition(), cap) for a in hvtInvaders for cap in capsules]
              minCapsuleDist = min(distancesToCapsules)
              if minCapsuleDist <= 5:
                # HVT invader is close to a capsule
                features['invaderNearCapsule'] = 1
          else:
            # No HVT invaders, proceed as usual
            distances = [self.getMazeDistance(myPos, a.getPosition()) for a in invaders]
            minInvaderDist = min(distances)
            features['invaderDistance'] = minInvaderDist
        else:
          # Patrol
          if self.target is None or self.target == myPos:
            self.target = self.selectPatrolPoint(successor)
          features['distanceToPatrol'] = self.getMazeDistance(myPos, self.target)

    elif self.currentRole == 'ReturnHome':
      # Compute distance to home
      homeBoundary = self.getHomeBoundary(gameState)
      minDistance = min([self.getMazeDistance(myPos, point) for point in homeBoundary])
      features['distanceToHome'] = minDistance

      # Avoid enemies
      enemies = [successor.getAgentState(i) for i in self.getOpponents(successor)]
      defenders = [a for a in enemies if not a.isPacman and a.getPosition() != None and a.scaredTimer <= 0]
      if len(defenders) > 0:
        distances = [self.getMazeDistance(myPos, a.getPosition()) for a in defenders]
        minDefenderDist = min(distances)
        if minDefenderDist <= 5:
          features['enemyDistance'] = minDefenderDist * minDefenderDist

          # Consider power capsules
        capsules = self.getCapsules(successor)
        if len(capsules) > 0:
          minCapsuleDist = min([self.getMazeDistance(myPos, cap) for cap in capsules])
          features['distanceToCapsule'] = minCapsuleDist

    # Don't stop or reverse unless necessary
    if action == Directions.STOP:
      features['stop'] = 1
    reverse = Directions.REVERSE[gameState.getAgentState(self.index).configuration.direction]
    if action == reverse:
      features['reverse'] = 1

    return features

  def getWeights(self, gameState, action):
    """
    Returns a dictionary of feature weights.
    """
    # To be adjusted
    if self.currentRole == 'Offense':
      return {'successorScore': 100, 'distanceToFood': -1, 'enemyDistance': 10, 'distanceToCapsule': -1, 'stop': -100, 'reverse': -2}
    elif self.currentRole == 'Defense':
      return {'numInvaders': -1000, 'invaderDistance': -10, 'invaderNearCapsule': -500, 'distanceToPatrol': -1, 'stop': -100, 'reverse': -2}
    elif self.currentRole == 'ReturnHome':
      return {'distanceToHome': -100, 'enemyDistance': 10, 'distanceToCapsule': -1, 'stop': -100, 'reverse': -2}

  def getSuccessor(self, gameState, action):
    """
    Finds the next successor which is a grid position.
    """
    successor = gameState.generateSuccessor(self.index, action)
    return successor

  def getHomeBoundary(self, gameState):
    """
    Returns a list of positions on the boundary between the home side and opponent's side.
    """
    layout = gameState.data.layout
    if self.red:
      midX = (layout.width // 2) - 1
    else:
      midX = layout.width // 2
    boundary = []
    for y in range(1, layout.height - 1):
      if not layout.walls[midX][y]:
        boundary.append((midX, y))
    return boundary

  def getAssignedFoods(self, gameState):
    """
    Assigns food to the agent based on proximity compared to teammate,
    and avoids overlapping with teammate's target.
    """
    myPos = gameState.getAgentState(self.index).getPosition()
    teammatePos = self.lastTeammatePos
    foods = self.getFood(gameState).asList()
    myFoods = []
    for food in foods:
      myDist = self.getMazeDistance(myPos, food)
      teammateDist = self.getMazeDistance(teammatePos, food) if teammatePos else float('inf')
      if myDist < teammateDist:
        myFoods.append(food)
      elif myDist == teammateDist:
        # Break tie by agent index
        if self.index < self.teammateIndex:
          myFoods.append(food)
    # Avoid teammate's target
    if self.teammateTarget in myFoods:
      myFoods.remove(self.teammateTarget)
    return myFoods

  def selectPatrolPoint(self, gameState):
    """
    Selects a patrol point for defensive agents.
    """
    patrolPoints = self.getPatrolPoints(gameState)
    return random.choice(patrolPoints)

  def getPatrolPoints(self, gameState):
    """
    Returns a list of patrol points on the home side for defensive agents,
    influenced by whether we can hold all food.

    Logic:
    - First, identify vertical hallways and pick one representative cell (middle) per run.
    - Then, if we can hold all food, filter patrol points to focus around defended food or critical areas.
    - If we cannot hold all food, return the broader set of patrol points for flexible positioning.
    """
    patrolPoints = []
    layout = gameState.data.layout

    # Determine the midpoint line based on the team
    midX = (layout.width // 2) - 1 if self.red else (layout.width // 2)
    xRange = range(1, midX) if self.red else range(midX + 1, layout.width - 1)

    for x in xRange:
      run = []
      for y in range(1, layout.height - 1):
        if not layout.walls[x][y]:
          # Part of a conmtinuous run of open cells
          run.append((x, y))
        else:
          # We hit a wall, select a patrol point if run is not empty
          if len(run) > 0:
            midIndex = len(run) // 2
            patrolPoints.append(run[midIndex])
            run = []
      if len(run) > 0:
        midIndex = len(run) // 2
        patrolPoints.append(run[midIndex])
        run = []

    if self.canHoldAllFood(gameState):
      # If we can hold all food, focus patrol points near defended food/capsules
      defendedFood = self.getFoodYouAreDefending(gameState).asList()
      capsules = self.getCapsulesYouAreDefending(gameState)
      criticalPoints = defendedFood + capsules

      if criticalPoints:
        # Filter patrolPoints to those closer to these critical points
        # pick a max distance threshold. Adjust as desired.
        maxDistanceThreshold = 7
        refinedPoints = []
        for p in patrolPoints:
          # If the patrol point is relatively close to any defended resource, keep it
          distances = [self.getMazeDistance(p, c) for c in criticalPoints]
          if distances and min(distances) <= maxDistanceThreshold:
            refinedPoints.append(p)
        # If filtering removes all points, fallback to original patrolPoints
        if refinedPoints:
          patrolPoints = refinedPoints

      # If no defended food or capsules, nothing special

    else:
      # should be able to do something... too tired
      pass

    return patrolPoints


  """
  Some helper methods
  """

  def isSafeToKeepEating(self, gameState):
    """
    Determine if it is safe to continue eating nearby dots.
    Conditions for safety:
    1. No enemy ghost is too close (e.g., closer than 5 steps).
    2. If an enemy ghost is close, you can still be safe if:
       - You can reach a power capsule before the enemy can catch you.
       OR
       - You can reach your home boundary before the enemy intercepts you.
    """
    myState = gameState.getAgentState(self.index)
    myPos = myState.getPosition()
    enemies = [gameState.getAgentState(i) for i in self.getOpponents(gameState)]
    enemyGhosts = [e for e in enemies if e.getPosition() is not None and not e.isPacman]
    carrying = myState.numCarrying

    # no visible enemy ghosts, safe to keep eating.
    if len(enemyGhosts) == 0:
      return True

    # Find the closest enemy ghost
    ghostDistances = [(ghost, self.getMazeDistance(myPos, ghost.getPosition())) for ghost in enemyGhosts]
    closestGhost, closestGhostDist = min(ghostDistances, key=lambda x: x[1])

    # Threshold for feeling threatened by an enemy ghost
    threatDistance = 5

    # If the closest ghost is far away, consider safe
    if closestGhostDist > threatDistance + carrying:
      return True

    # If my agent reach here, it means an enemy ghost is relatively close
    # Try to see if he or his teammates can grab a power capsule safely
    # capsule only leave for hvt (cuz it is limited)
    if carrying >= self.hvtThreshold:
      capsules = self.getCapsules(gameState)
      # Get positions of all friendly agents (including this one)
      friendlyPositions = [gameState.getAgentPosition(i) for i in self.getTeam(gameState)]

      # For each capsule, find the minimum distance from any friendly agent
      capsuleDistances = []
      for c in capsules:
        distancesToCapsule = [self.getMazeDistance(pos, c) for pos in friendlyPositions if pos is not None]
        if distancesToCapsule:
          capsuleDistances.append(min(distancesToCapsule))

      # Determine the closest capsule distance among all friendly agents
      closestCapsuleDist = min(capsuleDistances) if len(capsuleDistances) > 0 else float('inf')

      if closestCapsuleDist < closestGhostDist + 1:
        return True



    # If capsules won't/can't help, consider if you can return home safely
    homeBoundary = self.getHomeBoundary(gameState)
    if len(homeBoundary) > 0:
      homeDistances = [self.getMazeDistance(myPos, h) for h in homeBoundary]
      closestHomeDist = min(homeDistances) if homeDistances else float('inf')

      if carrying > self.hvtThreshold:
        if closestHomeDist + carrying < closestGhostDist:
          return True
      else:
        if closestHomeDist + 1 < closestGhostDist:
          return True

    # If none of the above conditions are met, it's not safe
    return False


  def canHoldAllFood(self, gameState):
    """
    Determine if your team can reliably hold all remaining food while on defense.
    Heuristic:
    - For each piece of defended food, check if a friendly agent can get there
      at least as quickly as any enemy agent.
    - If this is true for all food, return True.
    - Otherwise, return False.
    Notice here we are requiring our agent can reach food before enemy.
    It should be our agent can eat enemy before they escape
    but again, for simplicity
    """

    # Get defended food and capsule
    defendedFood = self.getFoodYouAreDefending(gameState).asList()
    capsules = self.getCapsulesYouAreDefending(gameState)
    defendedFood.extend(capsules)
    if len(defendedFood) == 0:
      # No food to defend
      return True

    myTeamIndices = self.getTeam(gameState)
    opponentIndices = self.getOpponents(gameState)
    friendlyPositions = [gameState.getAgentPosition(i) for i in myTeamIndices]
    enemyPositions = [gameState.getAgentPosition(i) for i in opponentIndices]

    # Filter out None positions (unseen enemies)
    enemyPositions = [pos for pos in enemyPositions if pos is not None]
    # If no known enemy positions, can't be sure, but often safer to assume True if you're ahead
    # if we can't see enemies, we assume they might be close.
    # treat unknown enemies as a risk and return False.
    if len(enemyPositions) == 0:
      # Without enemy info (I think this shouldn't occur through).
      return False

    # Check each food's accessibility
    for foodPos in defendedFood:
      # Distance for friendly agents
      friendlyDistances = [self.getMazeDistance(foodPos, fPos) for fPos in friendlyPositions if fPos is not None]
      if len(friendlyDistances) == 0:
        return False  # No friendly agent positions known, can't defend.

      minFriendlyDist = min(friendlyDistances)

      # Distance for enemy agents
      enemyDistances = [self.getMazeDistance(foodPos, ePos) for ePos in enemyPositions]
      if len(enemyDistances) == 0:
        # No known enemy positions, assume enemies might be anywhere
        # Being conservative, return False
        return False

      minEnemyDist = min(enemyDistances)

      # If any food that enemies can reach strictly sooner, we can't hold all food reliably
      if minEnemyDist < minFriendlyDist:
        return False

    # If we haven't returned False so far, it means for all food, we can reach as fast or faster than enemies.
    return True


  def whoShouldDefend(self, gameState, invaders):
    """
    Determine if at least one friendly agent can intercept all invaders alone.
    Returns the index of that agent if found, otherwise None.
    """
    if len(invaders) == 0:
      # No invaders
      return self.index

    myTeamIndices = self.getTeam(gameState)
    friendlyPositions = [(allyIndex, gameState.getAgentPosition(allyIndex))
                         for allyIndex in myTeamIndices
                         if gameState.getAgentPosition(allyIndex) is not None]

    if not friendlyPositions:
      # No known friendly positions (still, shouldn't be, just in case)
      return None

    # Determine invaders' escape boundary
    layout = gameState.data.layout
    if self.red:
      invaderBoundaryX = layout.width // 2
    else:
      invaderBoundaryX = (layout.width // 2) - 1

    def distanceToInvaderBoundary(pos):
      # Compute min distance to any open cell at invaders' boundary line
      boundaryPositions = [(invaderBoundaryX, by) for by in range(layout.height)
                           if not layout.walls[invaderBoundaryX][by]]
      if not boundaryPositions:
        return float('inf')
      return min(self.getMazeDistance(pos, bpos) for bpos in boundaryPositions)

    # Check each friendly agent
    for (allyIndex, allyPos) in friendlyPositions:
      canHandleAll = True
      for invader in invaders:
        invPos = invader.getPosition()
        if invPos is None:
          canHandleAll = False
          break
        agentToInvaderDist = self.getMazeDistance(allyPos, invPos)
        invaderEscapeDist = distanceToInvaderBoundary(invPos)

        # If the agent can intercept (reach invader at least as fast as invader can escape)
        if agentToInvaderDist > invaderEscapeDist + 1:
          canHandleAll = False
          break
      if canHandleAll:
        # This ally can handle all invaders alone
        return allyIndex

    return None

