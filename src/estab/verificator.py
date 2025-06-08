import src.estab.block as block

class NodeVerificator:
    
    """
    Verification of blockchain versions from nodes (v1)
    1. Look for exact matches
    2. Look for partition matches
    3. Look for complete different chains

    If exact matches is 51% and more:
    Choosing that chain, that have the most exact matches

    If there are no margin for exact matches:
    Choose the smallest chain, that contains in others
    
    """
    @staticmethod
    def fsync_verifacation(blockchain: list[list[dict]]) -> tuple[list[dict], str]:
        # Take chain that is the most popular
        for chain in blockchain:
            if blockchain.count(chain) / len(blockchain) >= 0.51:
                return chain, "most_popular"
        
        # Take the earliest chain
        is_all_len_eq = True
        p_l = len(blockchain[0])
        for chain in blockchain:
            if len(chain) != p_l:
                is_all_len_eq = False
                break
        
        if is_all_len_eq:
            cook = lambda d: block.Block.cook(d)

            lm, ch = cook(blockchain[0][-1]).timestamp, blockchain[0]
            for i in range(len(blockchain)):
                if cook(blockchain[i][-1]).timestamp < lm:
                    lm = cook(blockchain[i][-1]).timestamp
                    ch = blockchain[i]
            
            return ch, "earliest chain"

        # Take the longest chain
        lm, ch = 0, blockchain[0]
        for i in range(len(blockchain)):
            if len(blockchain[i]) > lm:
                lm = len(blockchain[i])
                ch = blockchain[i]
        
        return ch, "longest chain"
        
        # Take the smallest chain, that contains in others
        
        # n = dict()
        # for i in range(len(blockchain)):
        #     current = blockchain[i]
        #     for k in range(len(blockchain)):
        #         if i == k: continue
                
        #         if current == blockchain[k][:len(current)]:
        #             n[i] = 1 if not (i in n) else n[i] + 1
        
        # return blockchain[sorted(n)[-1]]