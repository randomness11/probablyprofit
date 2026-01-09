"""
Ensemble Agent

Multi-agent consensus engine that runs multiple AI models in parallel
and aggregates their decisions using configurable voting strategies.
"""

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter
from loguru import logger

from probablyprofit.agent.base import BaseAgent, Observation, Decision
from probablyprofit.api.client import PolymarketClient
from probablyprofit.api.exceptions import AgentException
from probablyprofit.risk.manager import RiskManager


class VotingStrategy(str, Enum):
    """Voting strategies for ensemble decisions."""
    MAJORITY = "majority"           # Simple majority wins
    WEIGHTED = "weighted"           # Weight by confidence
    UNANIMOUS = "unanimous"         # All must agree
    HIGHEST_CONFIDENCE = "highest"  # Trust most confident agent


class EnsembleAgent(BaseAgent):
    """
    Multi-agent consensus engine.
    
    Runs multiple AI agents in parallel and aggregates their decisions
    using configurable voting strategies. This provides:
    - Reduced variance in decisions
    - Protection against single-model failures
    - Higher confidence in consensus decisions
    
    Example:
        ensemble = EnsembleAgent(
            client=client,
            risk_manager=risk,
            agents=[openai_agent, gemini_agent, claude_agent],
            voting_strategy=VotingStrategy.MAJORITY,
            min_agreement=2,
        )
        await ensemble.run()
    """

    def __init__(
        self,
        client: PolymarketClient,
        risk_manager: RiskManager,
        agents: List[BaseAgent],
        voting_strategy: VotingStrategy = VotingStrategy.MAJORITY,
        min_agreement: int = 2,
        name: str = "EnsembleAgent",
        loop_interval: int = 60,
        strategy: Optional[Any] = None,
        dry_run: bool = False,
        timeout_seconds: float = 60.0,
    ):
        """
        Initialize ensemble agent.

        Args:
            client: Polymarket API client
            risk_manager: Risk management system
            agents: List of AI agents to run in parallel
            voting_strategy: How to aggregate decisions
            min_agreement: Minimum agents that must agree (for majority/unanimous)
            name: Agent name
            loop_interval: Seconds between loop iterations
            strategy: Optional strategy to filter markets
            dry_run: If True, log decisions but don't place real trades
            timeout_seconds: Max time to wait for agent decisions
        """
        super().__init__(client, risk_manager, name, loop_interval, strategy=strategy, dry_run=dry_run)
        
        if len(agents) < 2:
            raise ValueError("Ensemble requires at least 2 agents")
        
        self.agents = agents
        self.voting_strategy = voting_strategy
        self.min_agreement = min(min_agreement, len(agents))
        self.timeout_seconds = timeout_seconds
        
        agent_names = [a.name for a in agents]
        logger.info(
            f"EnsembleAgent '{name}' initialized with {len(agents)} agents: {agent_names}\n"
            f"  Voting: {voting_strategy.value}, Min agreement: {self.min_agreement}"
        )

    async def _get_agent_decision(
        self, agent: BaseAgent, observation: Observation
    ) -> Tuple[str, Optional[Decision], Optional[Exception]]:
        """
        Get decision from a single agent with error handling.
        
        Returns:
            Tuple of (agent_name, decision_or_none, error_or_none)
        """
        try:
            decision = await asyncio.wait_for(
                agent.decide(observation),
                timeout=self.timeout_seconds
            )
            return (agent.name, decision, None)
        except asyncio.TimeoutError:
            logger.warning(f"Agent '{agent.name}' timed out after {self.timeout_seconds}s")
            return (agent.name, None, TimeoutError(f"Timeout after {self.timeout_seconds}s"))
        except Exception as e:
            logger.warning(f"Agent '{agent.name}' failed: {e}")
            return (agent.name, None, e)

    async def _collect_decisions(
        self, observation: Observation
    ) -> List[Tuple[str, Decision]]:
        """
        Collect decisions from all agents in parallel.
        
        Returns:
            List of (agent_name, decision) tuples for successful agents
        """
        tasks = [
            self._get_agent_decision(agent, observation)
            for agent in self.agents
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=False)
        
        successful = []
        failed = []
        
        for agent_name, decision, error in results:
            if decision is not None:
                successful.append((agent_name, decision))
            else:
                failed.append((agent_name, str(error)))
        
        if failed:
            logger.warning(f"Failed agents: {failed}")
        
        logger.info(f"Collected {len(successful)}/{len(self.agents)} decisions")
        return successful

    def _aggregate_majority(
        self, decisions: List[Tuple[str, Decision]]
    ) -> Decision:
        """
        Aggregate decisions using simple majority voting.
        
        The action with the most votes wins. If there's a tie,
        we prefer 'hold' for safety.
        """
        if not decisions:
            return Decision(action="hold", reasoning="No agent decisions available")
        
        # Count actions
        action_counts = Counter(d.action for _, d in decisions)
        most_common = action_counts.most_common()
        
        # Check for tie
        if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
            # Tie - prefer hold for safety
            if "hold" in [a for a, _ in most_common[:2]]:
                winning_action = "hold"
            else:
                winning_action = most_common[0][0]
            logger.info(f"Vote tie, selecting: {winning_action}")
        else:
            winning_action = most_common[0][0]
        
        vote_count = action_counts[winning_action]
        
        # Check minimum agreement
        if vote_count < self.min_agreement:
            logger.warning(
                f"Only {vote_count} agents agreed on '{winning_action}', "
                f"need {self.min_agreement}. Defaulting to hold."
            )
            return Decision(
                action="hold",
                reasoning=f"Insufficient consensus: {vote_count}/{self.min_agreement} agents agreed",
                confidence=0.3
            )
        
        # Get all decisions that voted for winning action
        winning_decisions = [d for _, d in decisions if d.action == winning_action]
        
        # Aggregate the winning decisions
        return self._merge_decisions(winning_decisions, winning_action, vote_count, len(decisions))

    def _aggregate_weighted(
        self, decisions: List[Tuple[str, Decision]]
    ) -> Decision:
        """
        Aggregate decisions weighted by confidence scores.
        
        Each agent's vote is weighted by their confidence.
        """
        if not decisions:
            return Decision(action="hold", reasoning="No agent decisions available")
        
        # Calculate weighted scores for each action
        action_weights: Dict[str, float] = {}
        action_decisions: Dict[str, List[Decision]] = {}
        
        for _, decision in decisions:
            action = decision.action
            weight = decision.confidence
            
            if action not in action_weights:
                action_weights[action] = 0.0
                action_decisions[action] = []
            
            action_weights[action] += weight
            action_decisions[action].append(decision)
        
        # Find action with highest weighted score
        winning_action = max(action_weights, key=action_weights.get)
        winning_weight = action_weights[winning_action]
        total_weight = sum(action_weights.values())
        
        logger.info(
            f"Weighted vote: {winning_action} ({winning_weight:.2f}/{total_weight:.2f} = "
            f"{winning_weight/total_weight:.0%})"
        )
        
        # Merge winning decisions
        winning = action_decisions[winning_action]
        return self._merge_decisions(
            winning, winning_action, len(winning), len(decisions),
            confidence_boost=winning_weight / total_weight
        )

    def _aggregate_unanimous(
        self, decisions: List[Tuple[str, Decision]]
    ) -> Decision:
        """
        Require unanimous agreement from all agents.
        
        If not unanimous, default to hold.
        """
        if not decisions:
            return Decision(action="hold", reasoning="No agent decisions available")
        
        actions = set(d.action for _, d in decisions)
        
        if len(actions) == 1:
            # Unanimous!
            winning_action = actions.pop()
            all_decisions = [d for _, d in decisions]
            logger.info(f"Unanimous decision: {winning_action}")
            return self._merge_decisions(
                all_decisions, winning_action, len(decisions), len(decisions),
                confidence_boost=0.2  # Boost confidence for unanimous
            )
        else:
            # Not unanimous
            logger.info(f"No unanimity. Actions: {actions}")
            return Decision(
                action="hold",
                reasoning=f"No unanimous agreement. Actions proposed: {actions}",
                confidence=0.3
            )

    def _aggregate_highest_confidence(
        self, decisions: List[Tuple[str, Decision]]
    ) -> Decision:
        """
        Trust the agent with highest confidence.
        """
        if not decisions:
            return Decision(action="hold", reasoning="No agent decisions available")
        
        # Find decision with highest confidence
        best_agent, best_decision = max(decisions, key=lambda x: x[1].confidence)
        
        logger.info(
            f"Highest confidence: {best_agent} with {best_decision.confidence:.0%} "
            f"-> {best_decision.action}"
        )
        
        # Add metadata about selection
        best_decision.metadata["selected_agent"] = best_agent
        best_decision.metadata["selection_method"] = "highest_confidence"
        
        return best_decision

    def _merge_decisions(
        self,
        decisions: List[Decision],
        action: str,
        vote_count: int,
        total_agents: int,
        confidence_boost: float = 0.0,
    ) -> Decision:
        """
        Merge multiple agreeing decisions into one.
        
        For buy/sell, we need to pick consistent market_id, outcome, etc.
        """
        if not decisions:
            return Decision(action="hold", reasoning="No decisions to merge")
        
        # Average confidence
        avg_confidence = sum(d.confidence for d in decisions) / len(decisions)
        final_confidence = min(1.0, avg_confidence + confidence_boost)
        
        # For buy/sell, find most common market choice
        if action in ["buy", "sell"]:
            market_votes = Counter(
                (d.market_id, d.outcome) 
                for d in decisions 
                if d.market_id and d.outcome
            )
            
            if not market_votes:
                # No valid market selections
                return Decision(
                    action="hold",
                    reasoning="Agents agreed on action but not on market",
                    confidence=0.3
                )
            
            (market_id, outcome), market_count = market_votes.most_common(1)[0]
            
            # Average size and price from agreeing decisions
            agreeing = [d for d in decisions if d.market_id == market_id and d.outcome == outcome]
            avg_size = sum(d.size for d in agreeing) / len(agreeing)
            prices = [d.price for d in agreeing if d.price is not None]
            avg_price = sum(prices) / len(prices) if prices else None
            
            # Compile reasonings
            reasonings = [f"[{i+1}] {d.reasoning}" for i, d in enumerate(agreeing)]
            combined_reasoning = (
                f"ENSEMBLE ({vote_count}/{total_agents} agents agreed):\n" +
                "\n".join(reasonings[:3])  # Limit to 3 to avoid huge text
            )
            
            return Decision(
                action=action,
                market_id=market_id,
                outcome=outcome,
                size=avg_size,
                price=avg_price,
                reasoning=combined_reasoning,
                confidence=final_confidence,
                metadata={
                    "ensemble_vote": f"{vote_count}/{total_agents}",
                    "market_agreement": f"{market_count}/{len(decisions)}",
                }
            )
        else:
            # Hold action
            reasonings = [d.reasoning for d in decisions[:3]]
            combined_reasoning = (
                f"ENSEMBLE ({vote_count}/{total_agents} agents agreed to hold):\n" +
                "\n".join(f"[{i+1}] {r}" for i, r in enumerate(reasonings))
            )
            
            return Decision(
                action="hold",
                reasoning=combined_reasoning,
                confidence=final_confidence,
                metadata={"ensemble_vote": f"{vote_count}/{total_agents}"}
            )

    async def decide(self, observation: Observation) -> Decision:
        """
        Make a trading decision using ensemble voting.

        Args:
            observation: Current market observation

        Returns:
            Aggregated decision from all agents

        Raises:
            AgentException: If all agents fail
        """
        logger.info(f"[{self.name}] Collecting decisions from {len(self.agents)} agents...")
        
        # Collect decisions in parallel
        decisions = await self._collect_decisions(observation)
        
        if not decisions:
            raise AgentException("All agents failed to produce decisions")
        
        # Log individual decisions
        for agent_name, decision in decisions:
            logger.info(
                f"  {agent_name}: {decision.action} "
                f"(conf: {decision.confidence:.0%}, "
                f"market: {decision.market_id or 'N/A'})"
            )
        
        # Aggregate based on strategy
        if self.voting_strategy == VotingStrategy.MAJORITY:
            final = self._aggregate_majority(decisions)
        elif self.voting_strategy == VotingStrategy.WEIGHTED:
            final = self._aggregate_weighted(decisions)
        elif self.voting_strategy == VotingStrategy.UNANIMOUS:
            final = self._aggregate_unanimous(decisions)
        elif self.voting_strategy == VotingStrategy.HIGHEST_CONFIDENCE:
            final = self._aggregate_highest_confidence(decisions)
        else:
            final = self._aggregate_majority(decisions)
        
        logger.info(
            f"[{self.name}] Final decision: {final.action} "
            f"(confidence: {final.confidence:.0%})"
        )
        
        return final
